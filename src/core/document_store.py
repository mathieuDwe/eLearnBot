"""💾 Stockage documentaire JSON (remplace ChromaDB).

Stocke les textes extraits et métadonnées dans un fichier JSON local.
Avec backup/restore vers Supabase Storage pour la persistance cloud.

Chaque document stocke un `content_hash` (SHA256 du fichier source)
pour détecter les modifications et déclencher une ré-indexation automatique."""

import hashlib
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

_HASH_ALGORITHM = "sha256"  # Algorithme de hachage pour le suivi des versions

# ── Mots vides pour la recherche ─────────────────────────────────────────
_STOPWORDS = {
    "dans", "avec", "cette", "entre", "avoir", "faire", "tout", "plus",
    "pour", "sur", "dont", "leurs", "ainsi", "mais", "donc", "alors",
    "bien", "très", "fait", "être", "peut", "sont", "leur", "nous",
    "vous", "elles", "ils", "elle", "quel", "quels", "quelle", "quelles",
    "parce", "comme", "chez", "sans", "dans", "avec", "aussi", "ni",
    "car", "où", "dont", "depuis", "pendant", "quand", "après", "avant",
    "les", "des", "une", "cet", "celle", "ceux", "aux",
}


# ── Gestion du fichier JSON local ───────────────────────────────────────

def _load_documents() -> list[dict]:
    """Charge la liste des documents depuis le fichier JSON local.

    Retourne [] si :
      - Le fichier n'existe pas
      - Le JSON est invalide (corrompu)
      - La racine n'est pas une liste (résilience)
    """
    if not os.path.exists(_DOCUMENTS_FILE):
        return []
    try:
        with open(_DOCUMENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            # Fichier JSON valide mais pas une liste → silencieux
            return []
        return data
    except (json.JSONDecodeError, FileNotFoundError, ValueError):
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

def compute_content_hash(file_bytes: bytes) -> str:
    """Calcule le hash SHA256 d'un fichier pour le suivi de version.

    Args:
        file_bytes: Contenu du fichier en bytes.

    Returns:
        Empreinte hexadécimale SHA256.
    """
    return hashlib.sha256(file_bytes).hexdigest()


def get_document_by_filename(filename: str) -> Optional[dict]:
    """Retourne un document complet par son nom de fichier.

    Args:
        filename: Nom du fichier recherché.

    Returns:
        Dict complet du document, ou None si introuvable.
    """
    docs = _load_documents()
    for d in docs:
        if d["filename"] == filename:
            return d
    return None


def add_document(
    text: str,
    filename: str,
    metadata: dict = None,
    content_hash: str = None,
) -> str:
    """Ajoute un document à la base locale.

    Découpe le texte en chunks et stocke le tout dans le JSON.
    Si un document avec le même ``filename`` existe déjà, il est
    remplacé (mise à jour). Le ``content_hash`` permet de détecter
    les modifications du fichier source.

    Args:
        text: Texte complet du document.
        filename: Nom du fichier.
        metadata: Métadonnées additionnelles.
        content_hash: Empreinte SHA256 du fichier source (optionnel).

    Returns:
        ID du document.
    """
    metadata = metadata or {}
    doc_id = str(uuid.uuid4())

    # Découper en chunks
    chunks = chunk_text(text)

    # Ajouter le hash de contenu au metadata pour le suivi de version
    # Priorité au paramètre explicite, sinon on lit depuis metadata
    if content_hash:
        metadata["content_hash"] = content_hash
        metadata["hash_algorithm"] = _HASH_ALGORITHM
    elif "content_hash" in metadata:
        # Déjà présent dans metadata (ex: upload depuis professeur)
        metadata.setdefault("hash_algorithm", _HASH_ALGORITHM)

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

    Ignore silencieusement les documents corrompus (clés manquantes).

    Returns:
        Liste de dicts avec les infos des documents.
        Chaque entrée contient 'filename', 'chunks', 'metadata'
        et éventuellement 'content_hash'.
    """
    docs = _load_documents()
    result = []
    for d in docs:
        try:
            meta = d.get("metadata") or {}
            result.append({
                "filename": d.get("filename", "inconnu"),
                "chunks": d.get("chunks_count", 0),
                "text_length": len(d.get("text", "")),
                "metadata": meta,
                "content_hash": meta.get("content_hash"),
            })
        except (TypeError, ValueError, AttributeError):
            # Document corrompu → ignoré silencieusement
            continue
    return result


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

    Garantit que la progression est toujours > 0 pour éviter les boucles
    infinies. Si overlap >= chunk_size, overlap est réduit à chunk_size - 1.

    Args:
        text: Texte à découper.
        chunk_size: Nombre de mots par chunk.
        overlap: Nombre de mots de recouvrement.

    Returns:
        Liste de chunks de texte.
    """
    words = text.split()
    chunks = []

    if not words:
        return [""]

    if len(words) <= chunk_size:
        return [text]

    # Sécurité : la progression doit être au moins 1
    step = max(chunk_size - overlap, 1)

    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start += step

    return chunks


def _extract_keywords(text: str) -> set[str]:
    """Extrait les mots-clés significatifs d'une question.

    Garde les mots de 3+ caractères hors stopwords.
    """
    words = re.findall(r"[a-zA-ZéèêëàâîïôûùçÉÈÊËÀÂÎÏÔÛÙÇ]{2,}", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) >= 3}
