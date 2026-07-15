"""🔄 Pipeline de recherche vectorielle (Retrieval).

Sans LLM : regroupe les résultats par document et affiche une vue
synthétique — pas de copier-coller de texte brut dans la réponse."""

import re
from collections import defaultdict

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


def _format_size(size_bytes: int) -> str:
    """Formate une taille en bytes vers une lisible (Ko, Mo)."""
    if size_bytes < 1024:
        return f"{size_bytes} o"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} Ko"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} Mo"


def _truncate(text: str, max_len: int = 150) -> str:
    """Tronque un texte avec une ellipse si nécessaire."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rsplit(" ", 1)[0] + "…"


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

    Sans LLM : regroupe les résultats par document et affiche les noms
    et métadonnées. Le texte brut est relégué dans l'expander Sources.

    Args:
        question: La question posée par l'utilisateur.
        document_name: Filtrer sur un document spécifique.

    Returns:
        Dict avec 'answer' (str) — vue documentaire sans texte brut,
        et 'sources' (list[str]) — extraits pertinents.
    """
    store = get_vector_store()

    # Filtrer par document si spécifié
    filter_dict = None
    if document_name:
        filter_dict = {"filename": document_name}

    # Recherche des chunks pertinents
    results = store.search(
        query=question,
        n_results=15,
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

    # ── Regrouper les chunks par document ─────────────────────────────
    docs = defaultdict(list)
    for r in results:
        fname = r['metadata'].get('filename', 'Source inconnue')
        docs[fname].append(r)

    # Trier les documents par score max décroissant
    doc_scores = {}
    for fname, chunks_list in docs.items():
        doc_scores[fname] = max(1 - c['score'] for c in chunks_list)

    sorted_docs = sorted(doc_scores.items(), key=lambda x: -x[1])

    # ── Réponse : uniquement la fiche documentaire ───────────────────
    answer_parts = [
        f"🔍 **{len(docs)} document(s) trouvé(s)** "
        f"pour votre question :\n"
    ]

    for i, (fname, best_score) in enumerate(sorted_docs, 1):
        chunks_list = docs[fname]
        meta = chunks_list[0]['metadata']
        content_type = meta.get("content_type", "pdf")

        # Icône et type
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

        # Métadonnées affichables
        meta_lines = []
        meta_lines.append(f"📂 **Type :** {type_label}")

        # Durée pour les vidéos
        duration = meta.get("duration_display", "")
        if duration:
            meta_lines.append(f"⏱ **Durée :** {duration}")

        # Taille du fichier
        file_size = meta.get("size", 0)
        if file_size:
            meta_lines.append(f"💾 **Taille :** {_format_size(file_size)}")

        # Nombre de chunks
        meta_lines.append(f"🔢 **Passages :** {len(chunks_list)}")

        score_pct = best_score * 100
        meta_lines.append(f"📊 **Pertinence :** {score_pct:.1f}%")

        answer_parts.append(
            f"---\n\n"
            f"{icon} **{fname}**\n\n"
            + "\n".join(f"  {l}" for l in meta_lines)
        )

    # ── Sources : extraits pertinents par document ──────────────────
    sources = []
    for fname, _ in sorted_docs:
        chunks_list = docs[fname]

        source_parts = [f"📄 **{fname}** — passages pertinents :\n"]
        for j, c in enumerate(chunks_list[:3], 1):  # top 3 chunks/doc
            score_pct = (1 - c['score']) * 100
            text_snippet = _truncate(c['text'], 300)
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
    """Retourne la liste des documents indexés.

    Returns:
        Liste de dicts avec les infos des documents.
    """
    store = get_vector_store()
    return store.get_documents_list()
