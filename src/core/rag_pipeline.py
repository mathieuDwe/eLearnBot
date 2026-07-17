"""🔄 Pipeline de réponse aux questions.

Avec cache : si la question a déjà été posée, pas d'appel LLM.
Si LLM dispo : réponse générée avec le contexte des cours.
Sinon : utilise le moteur Q&A sans LLM (BM25 + stratégies).

Triple mode de réponse :
1.  Cache → réponse immédiate
2.  LLM dispo → réponse générée avec Groq/Gemini/Mammouth
3.  Pas de LLM → réponse du moteur non_llm (9 stratégies)
"""

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
    """Indexe un document ET lance son analyse pour le Q&A sans LLM.

    Args:
        text: Texte complet du document.
        filename: Nom du fichier.
        metadata: Métadonnées additionnelles.

    Returns:
        ID du document.
    """
    # 1. Stocker le document
    doc_id = document_store.add_document(text, filename, metadata)

    # 2. Lancer l'analyse non-LLM (silencieuse si échec)
    try:
        from core.non_llm import analyze_document as _analyze
        _analyze(text, filename)
    except Exception as e:
        # L'analyse non-LLM est un bonus, pas bloquante
        import logging
        logging.getLogger("rag_pipeline").warning(
            "Analyse non-LLM échouée pour '%s' : %s", filename, e
        )

    return doc_id


# ── Réponse ──────────────────────────────────────────────────────────────

def answer_question(
    question: str,
    document_name: str = None,
) -> dict:
    """Répond à une question avec 3 modes de réponse possibles.

    Trile mode :
    1. Cache → réponse immédiate si déjà posée
    2. LLM configuré → réponse générée avec le contexte des cours
    3. Pas de LLM → réponse du moteur non_llm (9 stratégies sans LLM)

    Args:
        question: Question en langage naturel.
        document_name: Filtrer sur un document spécifique (ou None).

    Returns:
        Dict avec "answer" (str) et optionnellement "sources" (list).
    """

    # ── 1. Vérifier le cache ────────────────────────────────────────
    cached = response_cache.get(question)
    if cached is not None:
        return cached

    # ── 2. Vérifier si un LLM est configuré ─────────────────────────
    has_llm = bool(_get_configured_providers())

    if has_llm:
        # ── 2a. Mode LLM : recherche + génération ───────────────────
        return _answer_with_llm(question, document_name)
    else:
        # ── 2b. Mode sans LLM : moteur non_llm ─────────────────────
        return _answer_without_llm(question, document_name)


def _answer_with_llm(question: str, document_name: str = None) -> dict:
    """Mode LLM : recherche les passages et génère une réponse via LLM."""
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

    # Construire le contexte pour le LLM
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

    # Fallback si tous les LLM ont échoué
    return _answer_without_llm(question, document_name)


def _answer_without_llm(question: str, document_name: str = None) -> dict:
    """Mode sans LLM : utilise le moteur non_llm (BM25 + 9 stratégies).

    Si le moteur non_llm n'est pas disponible (import error), utilise
    la vue documentaire basique comme fallback.
    """
    try:
        from core.non_llm import answer_question_non_llm

        result = answer_question_non_llm(
            question=question,
            document_name=document_name,
            min_confidence=0.0,
        )

        answer_text = result.get("answer", "")
        sources = result.get("sources", [])
        confidence = result.get("confidence", 0.0)
        strategy = result.get("strategy_used", "unknown")

        if not answer_text:
            return _basic_fallback(question, document_name)

        # Ajouter une indication de la stratégie utilisée
        if confidence < 0.4:
            prefix = "📚 **Recherche documentaire**\n\n"
        elif confidence < 0.7:
            prefix = "📖 **Réponse extraite des cours**\n\n"
        else:
            prefix = "✅ **Réponse trouvée dans les cours**\n\n"

        result_final = {
            "answer": prefix + answer_text,
            "sources": sources,
        }
        response_cache.set(question, result_final["answer"], result_final["sources"])
        return result_final

    except ImportError:
        # Module non_llm pas installé → fallback basique
        return _basic_fallback(question, document_name)
    except Exception as e:
        import logging
        logging.getLogger("rag_pipeline").error(
            "Moteur non_llm échoué : %s", e
        )
        return _basic_fallback(question, document_name)


def _basic_fallback(question: str, document_name: str = None) -> dict:
    """Fallback ultime : vue documentaire basique (sans LLM, sans non_llm)."""
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

    docs = defaultdict(list)
    for r in results:
        fname = r['metadata'].get('filename', 'Source inconnue')
        docs[fname].append(r)

    doc_scores = {f: max(r['score'] for r in cl) for f, cl in docs.items()}
    sorted_docs = sorted(doc_scores.items(), key=lambda x: -x[1])

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
