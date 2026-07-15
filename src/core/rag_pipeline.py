"""🔄 Pipeline de recherche vectorielle (Retrieval).

Sans LLM : extrait les phrases pertinentes des cours et les présente
sous forme de réponse synthétique — pas de copier-coller brut."""

import re

from core.pdf_extractor import chunk_text
from core.vector_store import get_vector_store


# ── Mots vides ───────────────────────────────────────────────────────────
_STOPWORDS = {
    "dans", "avec", "cette", "entre", "avoir", "faire", "tout", "plus",
    "pour", "sur", "dont", "leurs", "ainsi", "mais", "donc", "alors",
    "bien", "très", "fait", "être", "peut", "sont", "leur", "nous",
    "vous", "elles", "ils", "elle", "quel", "quels", "quelle", "quelles",
    "parce", "comme", "chez", "sans", "dans", "avec", "aussi", "ni",
    "car", "où", "dont", "depuis", "pendant", "quand", "après", "avant",
}


def _extract_keywords(text: str) -> set[str]:
    """Extrait les mots-clés significatifs d'une question.

    Garde les mots de 4+ caractères hors stopwords.
    """
    words = re.findall(r"[a-zA-ZéèêëàâîïôûùçÉÈÊËÀÂÎÏÔÛÙÇ]{2,}", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) >= 3}


def _split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def _extract_relevant_sentences(
    chunk_text: str,
    keywords: set[str],
    max_sentences: int = 3,
) -> str:
    """Extrait les phrases les plus pertinentes d'un chunk.

    Les phrases sont scorées selon le nombre de mots-clés de la question
    qu'elles contiennent. Seules les meilleures sont conservées.

    Args:
        chunk_text: Texte du chunk à analyser.
        keywords: Mots-clés extraits de la question.
        max_sentences: Nombre maximum de phrases à garder.

    Returns:
        Texte concaténé des phrases les plus pertinentes.
    """
    if not keywords:
        # Aucun mot-clé identifiable → premières phrases du chunk
        sentences = _split_sentences(chunk_text)
        return " ".join(sentences[:min(2, len(sentences))]) if sentences else chunk_text[:300]

    sentences = _split_sentences(chunk_text)
    scored = []

    for s in sentences:
        s_lower = s.lower()
        score = sum(1 for k in keywords if k in s_lower)
        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: (-x[0], len(x[1])))  # plus de matchs, puis plus court

    if not scored:
        # Fallback : retourner un extrait du début du chunk
        sentences = _split_sentences(chunk_text)
        return sentences[0] if sentences else chunk_text[:200]

    selected = [s for _, s in scored[:max_sentences]]

    # Supprimer les doublons (phrases quasi-identiques)
    deduped = []
    seen = set()
    for s in selected:
        key = s.lower()[:60]
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    return " ".join(deduped)


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

    Sans LLM : extrait les phrases pertinentes de chaque passage
    par rapport à la question posée (matching de mots-clés).

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

    # Extraire les mots-clés de la question
    keywords = _extract_keywords(question)

    # Construire une réponse synthétique
    answer_parts = [
        f"🔍 **{len(results)} extrait(s) trouvé(s)** dans les cours :\n"
    ]
    sources = []

    for i, r in enumerate(results, 1):
        filename = r['metadata'].get('filename', 'Source inconnue')
        score_pct = (1 - r['score']) * 100
        full_text = r['text']

        # Extraire uniquement les phrases pertinentes
        relevant = _extract_relevant_sentences(full_text, keywords)

        # Tronquer si la réponse est encore trop longue
        if len(relevant) > 400:
            relevant = relevant[:397] + "…"

        answer_parts.append(
            f"---\n\n"
            f"📄 **Extrait {i}** — *{filename}*\n"
            f"📊 **Pertinence :** {score_pct:.1f}%\n\n"
            f"> {relevant}"
        )

        # Source plus complète dans l'expander
        source_full = full_text[:500]
        if len(full_text) > 500:
            source_full += "\n*(… suite tronquée, voir le document complet)*"
        sources.append(
            f"{filename} (score: {score_pct:.1f}%)\n\n"
            f"> {source_full}"
        )

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