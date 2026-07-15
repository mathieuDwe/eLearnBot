"""🔄 Pipeline de recherche documentaire.

Sans LLM ni ChromaDB : stockage JSON local + recherche par mots-clés."""

import re

from core import document_store
from core.pdf_extractor import chunk_text as pdf_chunk_text


def _split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def _extract_relevant_sentences(
    chunk_text: str,
    keywords: set[str] | None = None,
    max_sentences: int = 3,
) -> str:
    """Extrait les phrases les plus pertinentes d'un chunk.

    Args:
        chunk_text: Texte du chunk.
        keywords: Mots-clés ou None (retourne le début).
        max_sentences: Nombre max de phrases.

    Returns:
        Texte concaténé des phrases pertinentes.
    """
    if not keywords:
        sentences = _split_sentences(chunk_text)
        return " ".join(sentences[:min(2, len(sentences))]) if sentences else chunk_text[:300]

    sentences = _split_sentences(chunk_text)
    scored = []

    for s in sentences:
        s_lower = s.lower()
        score = sum(1 for k in keywords if k in s_lower)
        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: (-x[0], len(x[1])))

    if not scored:
        sentences = _split_sentences(chunk_text)
        return sentences[0] if sentences else chunk_text[:200]

    selected = [s for _, s in scored[:max_sentences]]

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
    """Indexe un document dans le stockage local.

    1. Découpe le texte en chunks
    2. Stocke dans le fichier JSON

    Args:
        text: Texte complet du document.
        filename: Nom du fichier.
        metadata: Métadonnées additionnelles.

    Returns:
        ID du document.
    """
    return document_store.add_document(text, filename, metadata)


def answer_question(
    question: str,
    document_name: str = None,
) -> dict:
    """Cherche les passages pertinents dans les cours.

    Mots-clés + phrases pertinentes — pas de LLM, pas de vecteurs.

    Args:
        question: La question posée.
        document_name: Filtrer sur un document spécifique.

    Returns:
        Dict avec 'answer' (str) et 'sources' (list[str]).
    """
    # Recherche par mots-clés
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

    # Extraire les mots-clés de la question
    keywords = document_store._extract_keywords(question)

    # Regrouper par document
    from collections import defaultdict
    docs = defaultdict(list)
    for r in results:
        fname = r['metadata'].get('filename', 'Source inconnue')
        docs[fname].append(r)

    # Trier les documents par score max
    doc_scores = {}
    for fname, chunks_list in docs.items():
        doc_scores[fname] = max(r['score'] for r in chunks_list)

    sorted_docs = sorted(doc_scores.items(), key=lambda x: -x[1])

    # Réponse : fiches documentaires
    answer_parts = [
        f"🔍 **{len(docs)} document(s) trouvé(s)** "
        f"pour votre question :\n"
    ]

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

    # Sources : extraits par document
    sources = []
    for fname, _ in sorted_docs:
        chunks_list = docs[fname]
        source_parts = [f"📄 **{fname}** — passages pertinents :\n"]
        for j, c in enumerate(chunks_list[:3], 1):
            score_pct = c['score'] * 100
            text_snippet = c['text'][:300]
            if len(c['text']) > 300:
                text_snippet = c['text'][:297].rsplit(" ", 1)[0] + "…"
            source_parts.append(
                f"**Passage {j}** (pertinence: {score_pct:.1f}%)\n"
                f"> {text_snippet}"
            )
        if len(chunks_list) > 3:
            source_parts.append(
                f"\n*… et {len(chunks_list) - 3} autre(s) passage(s)*"
            )
        sources.append("\n\n".join(source_parts))

    return {
        "answer": "\n\n".join(answer_parts),
        "sources": sources,
    }


def get_available_documents() -> list[dict]:
    """Retourne la liste des documents indexés."""
    return document_store.get_documents_list()
