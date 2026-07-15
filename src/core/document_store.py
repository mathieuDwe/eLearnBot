"""💾 Stockage documentaire JSON (remplace ChromaDB).

Stocke les textes extraits et métadonnées dans un fichier JSON local.
Avec backup/restore vers Supabase Storage pour la persistance cloud."""

import json
import os
import re
import uuid
from collections import defaultdict
from typing import Optional

# ── Configuration ────────────────────────────────────────────────────────
_DATA_DIR = os.getenv("DATA_DIR", "./data")
_DOCUMENTS_FILE = os.path.join(_DATA_DIR, "documents.json")
_CLOUD_BACKUP_KEY = "documents_backup.json"

# ── Mots vides pour la recherche ─────────────────────────────────────────
_STOPWORDS = {
    "dans", "avec", "cette", "entre", "avoir", "faire", "tout", "plus",
    "pour", "sur", "dont", "leurs", "ainsi", "mais", "donc", "alors",
    "bien", "très", "fait", "être", "peut", "sont", "leur", "nous",
    "vous", "elles", "ils", "elle", "quel", "quels", "quelle", "quelles",
    "parce", "comme", "chez", "sans", "dans", "avec", "aussi", "ni",
    "car", "où", "dont", "depuis", "pendant", "quand", "après", "avant",
}


# ── Gestion du fichier JSON local ───────────────────────────────────────

def _load_documents() -> list[dict]:
    """Charge la liste des documents depuis le fichier JSON local."""
    if not os.path.exists(_DOCUMENTS_FILE):
        return []
    try:
        with open(_DOCUMENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_documents(docs: list[dict]):
    """Sauvegarde la liste des documents dans le fichier JSON local."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_DOCUMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False)


# ── Cloud backup (Supabase Storage) ──────────────────────────────────────

def _get_supabase_storage():
    """Retourne l'instance SupabaseStorage ou None."""
    try:
        from integrations.supabase_storage import SupabaseStorage
        return SupabaseStorage()
    except Exception:
        return None


def save_to_cloud():
    """Sauvegarde le fichier documents.json vers Supabase Storage."""
    storage = _get_supabase_storage()
    if storage is None:
        return

    if not os.path.exists(_DOCUMENTS_FILE):
        return

    try:
        with open(_DOCUMENTS_FILE, "rb") as f:
            data = f.read()
        storage.upload_bytes(data, _CLOUD_BACKUP_KEY, "application/json")
    except Exception as e:
        print(f"⚠️ Échec backup cloud : {e}")


def load_from_cloud():
    """Restaure le fichier documents.json depuis Supabase Storage."""
    storage = _get_supabase_storage()
    if storage is None:
        return

    try:
        data = storage.download_file(_CLOUD_BACKUP_KEY)
        if data:
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_DOCUMENTS_FILE, "wb") as f:
                f.write(data)
    except Exception as e:
        print(f"ℹ️ Aucun backup cloud trouvé : {e}")


# ── API publique ─────────────────────────────────────────────────────────

def add_document(
    text: str,
    filename: str,
    metadata: dict = None,
) -> str:
    """Ajoute un document à la base locale.

    Découpe le texte en chunks et stocke le tout dans le JSON.

    Args:
        text: Texte complet du document.
        filename: Nom du fichier.
        metadata: Métadonnées additionnelles.

    Returns:
        ID du document.
    """
    metadata = metadata or {}
    doc_id = str(uuid.uuid4())

    # Découper en chunks
    chunks = chunk_text(text)

    doc = {
        "id": doc_id,
        "filename": filename,
        "text": text,
        "chunks": chunks,
        "chunks_count": len(chunks),
        "metadata": metadata,
    }

    docs = _load_documents()

    # Remplacer si le même filename existe déjà
    existing = [d for d in docs if d["filename"] == filename]
    if existing:
        # Supprimer l'ancienne version
        docs = [d for d in docs if d["filename"] != filename]

    docs.append(doc)
    _save_documents(docs)
    save_to_cloud()

    return doc_id


def delete_document(filename: str) -> int:
    """Supprime un document par son nom.

    Args:
        filename: Nom du fichier à supprimer.

    Returns:
        Nombre de chunks supprimés.
    """
    docs = _load_documents()
    removed = [d for d in docs if d["filename"] == filename]
    docs = [d for d in docs if d["filename"] != filename]
    _save_documents(docs)
    save_to_cloud()
    return removed[0]["chunks_count"] if removed else 0


def get_documents_list() -> list[dict]:
    """Retourne la liste des documents disponibles.

    Returns:
        Liste de dicts avec les infos des documents.
    """
    docs = _load_documents()
    return [
        {
            "filename": d["filename"],
            "chunks": d["chunks_count"],
            "metadata": d["metadata"],
        }
        for d in docs
    ]


def search(
    query: str,
    n_results: int = 8,
    document_name: str = None,
) -> list[dict]:
    """Recherche les chunks les plus pertinents par mots-clés.

    Args:
        query: Texte de la requête.
        n_results: Nombre de résultats max.
        document_name: Filtrer sur un document spécifique.

    Returns:
        Liste de dicts avec 'text', 'score', 'metadata'.
    """
    docs = _load_documents()

    # Filtrer par document si demandé
    if document_name:
        docs = [d for d in docs if d["filename"] == document_name]

    if not docs:
        return []

    # Extraire les mots-clés de la requête
    keywords = _extract_keywords(query)

    if not keywords:
        # Pas de mots-clés → retourner les premiers chunks disponibles
        results = []
        for d in docs:
            meta = d.get("metadata", {})
            meta["filename"] = d["filename"]
            for chunk in d["chunks"][:3]:
                results.append({
                    "text": chunk,
                    "score": 0.5,
                    "metadata": dict(meta),
                })
        return results[:n_results]

    # Scorer chaque chunk par nombre de mots-clés présents
    scored = []
    for d in docs:
        meta = d.get("metadata", {})
        meta["filename"] = d["filename"]
        for chunk in d["chunks"]:
            chunk_lower = chunk.lower()
            score = sum(1 for k in keywords if k in chunk_lower)
            if score > 0:
                scored.append({
                    "text": chunk,
                    "score": score,
                    "metadata": dict(meta),
                })

    # Trier par score décroissant
    scored.sort(key=lambda x: -x["score"])

    # Normaliser les scores entre 0 et 1
    if scored:
        max_score = scored[0]["score"]
        if max_score > 0:
            for r in scored:
                r["score"] = r["score"] / max_score

    return scored[:n_results]


def count_documents() -> int:
    """Retourne le nombre total de documents."""
    return len(_load_documents())


# ── Helpers ──────────────────────────────────────────────────────────────

def _format_size(size_bytes: int) -> str:
    """Formate une taille en bytes vers une lisible (Ko, Mo)."""
    if size_bytes < 1024:
        return f"{size_bytes} o"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} Ko"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} Mo"


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Découpe un texte en chunks de taille fixe avec recouvrement.

    Args:
        text: Texte à découper.
        chunk_size: Nombre de mots par chunk.
        overlap: Nombre de mots de recouvrement.

    Returns:
        Liste de chunks de texte.
    """
    words = text.split()
    chunks = []

    if len(words) <= chunk_size:
        return [text]

    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


def _extract_keywords(text: str) -> set[str]:
    """Extrait les mots-clés significatifs d'une question.

    Garde les mots de 3+ caractères hors stopwords.
    """
    words = re.findall(r"[a-zA-ZéèêëàâîïôûùçÉÈÊËÀÂÎÏÔÛÙÇ]{2,}", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) >= 3}
