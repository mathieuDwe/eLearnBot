"""🔄 Pipeline RAG (Retrieval Augmented Generation)."""

import os
from typing import Optional

from core.pdf_extractor import chunk_text
from core.embeddings import get_embedder
from core.vector_store import get_vector_store


# ── Configuration LLM ────────────────────────────────────────────────────
def _get_llm_client():
    """Configure et retourne le client LLM selon les variables d'environnement."""
    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if groq_key:
        from groq import Groq
        return Groq(api_key=groq_key), "groq"
    elif openai_key:
        from openai import OpenAI
        return OpenAI(api_key=openai_key), "openai"
    elif gemini_key:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        return genai, "gemini"
    else:
        return None, "none"


def _get_default_model(provider: str) -> str:
    """Retourne le modèle par défaut selon le provider."""
    models = {
        "groq": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        "openai": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        "gemini": os.getenv("LLM_MODEL", "gemini-2.0-flash"),
    }
    return models.get(provider, "unknown")


def _call_llm(prompt: str) -> str:
    """Appelle le LLM configuré avec un prompt.

    Args:
        prompt: Le prompt complet à envoyer.

    Returns:
        La réponse textuelle du LLM.

    Raises:
        RuntimeError: Si aucun LLM n'est configuré.
    """
    client, provider = _get_llm_client()
    if client is None:
        return (
            "⚠️ Aucune clé API LLM configurée.\n\n"
            "Configurez GROQ_API_KEY, OPENAI_API_KEY ou GEMINI_API_KEY "
            "dans votre fichier .env pour activer les réponses IA.\n\n"
            "Voici les passages pertinents trouvés dans le cours :\n"
        )

    model = _get_default_model(provider)

    try:
        if provider == "groq":
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            return completion.choices[0].message.content

        elif provider == "openai":
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            return completion.choices[0].message.content

        elif provider == "gemini":
            model_instance = client.GenerativeModel(model)
            response = model_instance.generate_content(prompt)
            return response.text

    except Exception as e:
        return f"❌ Erreur lors de l'appel LLM : {e}"


# ── Pipeline principal ───────────────────────────────────────────────────


def index_document(
    text: str,
    filename: str,
    metadata: Optional[dict] = None,
) -> str:
    """Indexe un document dans la base vectorielle.

    1. Découpe le texte en chunks
    2. Génère les embeddings
    3. Stocke dans ChromaDB

    Args:
        text: Texte complet du document.
        filename: Nom du fichier.
        metadata: Métadonnées additionnelles.

    Returns:
        ID du document (premier chunk).
    """
    metadata = metadata or {}
    store = get_vector_store()

    # Découper en chunks
    chunks = chunk_text(text, chunk_size=500, overlap=50)

    if not chunks:
        return ""

    # Indexer
    ids = store.add_document(chunks, filename, metadata)
    return ids[0] if ids else ""


def answer_question(
    question: str,
    document_name: Optional[str] = None,
    n_results: int = 5,
) -> dict:
    """Répond à une question en utilisant le pipeline RAG.

    1. Recherche les chunks pertinents dans ChromaDB
    2. Construit un prompt avec le contexte
    3. Appelle le LLM pour générer la réponse

    Args:
        question: La question posée par l'utilisateur.
        document_name: Filtrer sur un document spécifique.
        n_results: Nombre de chunks à récupérer.

    Returns:
        Dict avec 'answer' (str) et 'sources' (list[str]).
    """
    store = get_vector_store()

    # Filtrer par document si spécifié
    filter_dict = None
    if document_name:
        filter_dict = {"filename": document_name}

    # Recherche des chunks pertinents
    results = store.search(
        query=question,
        n_results=n_results,
        filter_dict=filter_dict,
    )

    if not results:
        return {
            "answer": (
                "😕 Je n'ai pas trouvé de passages pertinents dans "
                "les cours pour répondre à votre question."
            ),
            "sources": [],
        }

    # Construction du contexte
    context_parts = []
    sources = []
    for i, r in enumerate(results, 1):
        context_parts.append(f"[Passage {i}]:\n{r['text']}")
        source_info = (
            f"{r['metadata'].get('filename', 'Source inconnue')} "
            f"(score: {1 - r['score']:.2%})"
        )
        sources.append(source_info)

    context = "\n\n---\n\n".join(context_parts)

    # Prompt RAG
    prompt = f"""Tu es un assistant pédagogique spécialisé dans l'aide aux élèves.
Tu réponds UNIQUEMENT à partir des passages de cours fournis ci-dessous.
Si les passages ne contiennent pas l'information, réponds honnêtement que tu ne sais pas.
Cite toujours le passage source entre crochets [Passage X] dans ta réponse.

Contexte issu des cours :
{context}

Question de l'élève : {question}

Réponse :"""

    # Appel LLM
    answer = _call_llm(prompt)

    return {
        "answer": answer,
        "sources": sources,
    }


def get_available_documents() -> list[dict]:
    """Retourne la liste des documents indexés.

    Returns:
        Liste de dicts avec les infos des documents.
    """
    store = get_vector_store()
    return store.get_documents_list()