"""🔄 Pipeline de réponse aux questions.

Avec cache : si la question a déjà été posée, pas d'appel LLM.
Si LLM dispo : réponse générée avec le contexte des cours.
Sinon : retourne la vue documentaire."""

import os
import re
from collections import defaultdict

from core import document_store, response_cache


# ── Configuration LLM ────────────────────────────────────────────────────

_PROVIDER_ERRORS: dict[str, str] = {}


def _get_configured_providers() -> list[tuple]:
    """Retourne tous les providers LLM configurés.

    Chaque tuple : (client, provider_name, model)
    L'ordre détermine la priorité d'appel."""
    providers = []

    groq_key = os.getenv("GROQ_API_KEY")
    mammouth_key = os.getenv("MAMMOUTH_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    llm_model = os.getenv("LLM_MODEL", "")

    if groq_key:
        try:
            from groq import Groq
            providers.append((
                Groq(api_key=groq_key),
                "groq",
                llm_model or "llama-3.3-70b-versatile",
            ))
        except ImportError:
            pass

    if mammouth_key:
        try:
            from openai import OpenAI
            providers.append((
                OpenAI(api_key=mammouth_key, base_url="https://api.mammouth.ai/v1"),
                "mammouth",
                llm_model or "kimi-k2.5",
            ))
        except ImportError:
            pass

    if gemini_key:
        try:
            from google import genai as genai_client
            providers.append((
                genai_client.Client(api_key=gemini_key),
                "gemini",
                llm_model or "gemini-2.0-flash",
            ))
        except ImportError:
            pass

    return providers


def _call_llm(prompt: str) -> str:
    """Appelle le premier LLM disponible avec fallback.

    Essaye chaque provider configuré dans l'ordre (Groq → Mammouth → Gemini).
    Si l'un échoue (rate limit, token épuisé, erreur serveur),
    passe automatiquement au suivant.

    Returns:
        Texte de la réponse, ou "" si tous les providers ont échoué.
    """
    providers = _get_configured_providers()
    if not providers:
        return ""

    for client, provider, model in providers:
        # Si ce provider a déjà échoué durant cette session, le sauter
        if _PROVIDER_ERRORS.get(provider) == "token_exhausted":
            continue

        try:
            if provider == "gemini":
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"temperature": 0.3, "max_output_tokens": 1024},
                )
                return response.text
            else:
                # groq, mammouth — tous OpenAI-compatibles
                completion = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1024,
                )
                return completion.choices[0].message.content

        except Exception as e:
            err_str = str(e).lower()
            if any(x in err_str for x in (
                "rate limit", "rate_limit", "429",
                "quota", "token exhausted", "insufficient",
                "resource exhausted", "too many requests",
            )):
                _PROVIDER_ERRORS[provider] = "token_exhausted"
            # Sinon (erreur auth, réseau, etc.) on réessaiera au prochain appel
            continue

    return ""


# ── Indexation ────────────────────────────────────────────────────────────

def index_document(
    text: str,
    filename: str,
    metadata: dict = None,
) -> str:
    return document_store.add_document(text, filename, metadata)


# ── Réponse ──────────────────────────────────────────────────────────────

def answer_question(
    question: str,
    document_name: str = None,
) -> dict:
    """Répond à une question avec cache + LLM (si dispo).

    1. Vérifie le cache → réponse immédiate si déjà posée
    2. Cherche les passages pertinents dans les cours
    3. Si LLM configuré : génère une réponse avec le contexte
    4. Si pas de LLM : retourne la vue documentaire (fallback)
    """

    # ── 1. Vérifier le cache ────────────────────────────────────────
    cached = response_cache.get(question)
    if cached is not None:
        return cached

    # ── 2. Recherche dans les documents ──────────────────────────────
    results = document_store.search(
        query=question,
        n_results=10,
        document_name=document_name,
    )

    if not results:
        return {
            "answer": (
                "😕 Je n'ai pas trouvé de passages pertinents dans "
                "les cours pour répondre à votre question."
            ),
            "sources": [],
        }

    # Regrouper par document
    docs = defaultdict(list)
    for r in results:
        fname = r['metadata'].get('filename', 'Source inconnue')
        docs[fname].append(r)

    doc_scores = {f: max(r['score'] for r in cl) for f, cl in docs.items()}
    sorted_docs = sorted(doc_scores.items(), key=lambda x: -x[1])

    # ── 3. Appel LLM (si configuré) ─────────────────────────────────
    if _get_configured_providers():
        # Construire le contexte
        context_parts = []
        source_list = []
        for i, (fname, _) in enumerate(sorted_docs, 1):
            for j, c in enumerate(docs[fname][:3], 1):
                context_parts.append(
                    f"[Source {i}.{j} — {fname}]:\n{c['text']}"
                )
            source_list.append(f"{fname}")

        context = "\n\n".join(context_parts)

        prompt = f"""Tu es un assistant pédagogique. Réponds à la question de l'élève
en t'appuyant UNIQUEMENT sur le contexte fourni ci-dessous.

Contexte (extraits des cours) :
{context}

Question : {question}

Réponds de façon claire et concise. Si le contexte ne contient pas
l'information, dis-le honnêtement."""

        answer = _call_llm(prompt)

        if answer:
            result = {
                "answer": answer,
                "sources": source_list,
            }
            response_cache.set(question, result["answer"], result["sources"])
            return result

    # ── 4. Fallback : vue documentaire (pas de LLM) ─────────────────
    answer_parts = [
        f"🔍 **{len(docs)} document(s) trouvé(s)** "
        f"pour votre question :\n"
    ]
    sources = []

    for i, (fname, best_score) in enumerate(sorted_docs, 1):
        chunks_list = docs[fname]
        meta = chunks_list[0]['metadata']
        content_type = meta.get("content_type", "pdf")

        doc_type = meta.get("type", "")
        if doc_type == "legal":
            icon = "⚖️"
            type_label = "Article juridique"
        elif content_type == "mp4":
            icon = "🎬"
            type_label = "Cours vidéo"
        else:
            icon = "📄"
            type_label = "Cours (PDF)"

        meta_lines = [f"📂 **Type :** {type_label}"]
        duration = meta.get("duration_display", "")
        if duration:
            meta_lines.append(f"⏱ **Durée :** {duration}")
        file_size = meta.get("size", 0)
        if file_size:
            from core.document_store import _format_size
            meta_lines.append(f"💾 **Taille :** {_format_size(file_size)}")
        meta_lines.append(f"🔢 **Passages :** {len(chunks_list)}")
        meta_lines.append(f"📊 **Pertinence :** {best_score * 100:.1f}%")

        answer_parts.append(
            f"---\n\n"
            f"{icon} **{fname}**\n\n"
            + "\n".join(f"  {l}" for l in meta_lines)
        )

        # Sources détaillées
        doc_src = [f"📄 **{fname}** — passages pertinents :\n"]
        for j, c in enumerate(chunks_list[:3], 1):
            score_pct = c['score'] * 100
            text = c['text'][:297].rsplit(" ", 1)[0] + "…" if len(c['text']) > 300 else c['text']
            doc_src.append(
                f"**Passage {j}** (pertinence: {score_pct:.1f}%)\n"
                f"> {text}"
            )
        if len(chunks_list) > 3:
            doc_src.append(f"\n*… et {len(chunks_list) - 3} autre(s) passage(s)*")
        sources.append("\n\n".join(doc_src))

    result = {
        "answer": "\n\n".join(answer_parts),
        "sources": sources,
    }
    response_cache.set(question, result["answer"], result["sources"])
    return result


def get_available_documents() -> list[dict]:
    return document_store.get_documents_list()
