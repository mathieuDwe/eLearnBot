"""🔄 Pipeline de recherche vectorielle (Retrieval).

Sans LLM : retourne les passages pertinents bruts trouvés dans les cours."""

from core.pdf_extractor import chunk_text
from core.vector_store import get_vector_store


def index_document(
    text: str,
    filename: str,
    metadata: dict = None,
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

    # Découper en chunks (plus grands pour les transcriptions vidéo)
    chunks = chunk_text(text, chunk_size=800, overlap=100)

    if not chunks:
        return ""

    # Indexer
    ids = store.add_document(chunks, filename, metadata)
    return ids[0] if ids else ""


def answer_question(
    question: str,
    document_name: str = None,
) -> dict:
    """Cherche les passages pertinents dans les cours indexés.

    Sans LLM : retourne directement les extraits de cours les plus
    pertinents par rapport à la question posée.

    Args:
        question: La question posée par l'utilisateur.
        document_name: Filtrer sur un document spécifique.

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
        n_results=8,
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

    # Construire la réponse à partir des passages bruts
    answer_parts = [
        f"🔍 **{len(results)} passage(s) trouvé(s)** pour votre question :\n"
    ]
    sources = []

    for i, r in enumerate(results, 1):
        filename = r['metadata'].get('filename', 'Source inconnue')
        score_pct = (1 - r['score']) * 100  # similarité en %

        answer_parts.append(
            f"---\n\n"
            f"📄 **Passage {i}** — *{filename}*\n"
            f"📊 **Pertinence :** {score_pct:.1f}%\n\n"
            f"> {r['text']}"
        )
        sources.append(f"{filename} (score: {score_pct:.1f}%)")

    return {
        "answer": "\n\n".join(answer_parts),
        "sources": sources,
    }


def get_available_documents() -> list[dict]:
    """Retourne la liste des documents indexés.

    Returns:
        Liste de dicts avec les infos des documents.
    """
    store = get_vector_store()
    return store.get_documents_list()