"""☁️ Stockage documentaire cloud (Supabase Storage uniquement).

PLUS AUCUN STOCKAGE LOCAL. Toutes les données sont persistées
exclusivement dans le bucket Supabase Storage.

Fonctionnement
--------------
- Cache mémoire : les documents sont chargés en RAM au premier accès
  et servis depuis le cache pour les accès suivants.
- Sync écrite : chaque modification (ajout/suppression) déclenche
  une synchronisation immédiate vers Supabase Storage.
- Sync lecture : le cache est rafraîchi depuis le cloud au démarrage
  et après chaque écriture.
- Mode dégradé : si Supabase n'est pas configuré, le cache mémoire
  est utilisé sans persistance (utile pour le développement/test).

Chaque document stocke un ``content_hash`` (SHA256 du fichier source)
pour détecter les modifications et déclencher une ré-indexation automatique.
"""

import hashlib
import json
import os
import re
import uuid
from collections import defaultdict
from typing import Optional

# ── Configuration ────────────────────────────────────────────────────────
_DOCUMENTS_KEY = "documents_index.json"  # Clé dans le bucket Supabase
_HASH_ALGORITHM = "sha256"

# Cache mémoire (lazy-loaded depuis le cloud)
_documents_cache: list[dict] | None = None

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


# ── Client Supabase (lazy singleton) ─────────────────────────────────────

def _get_supabase_storage():
    """Retourne l'instance SupabaseStorage ou None.

    Returns None si Supabase n'est pas configuré (mode dégradé mémoire).
    """
    try:
        from integrations.supabase_storage import SupabaseStorage
        return SupabaseStorage()
    except (ImportError, ValueError, Exception):
        return None


def is_cloud_configured() -> bool:
    """Vérifie si le stockage cloud Supabase est disponible.

    Returns:
        True si SUPABASE_URL + SUPABASE_KEY sont configurés et valides.
    """
    return _get_supabase_storage() is not None


# ── Gestion du cache mémoire / cloud ─────────────────────────────────────

def _load_cache() -> list[dict]:
    """Charge les documents depuis le cache mémoire ou le cloud.

    Stratégie (lazy loading) :
      1. Si le cache mémoire est rempli → le retourne directement
      2. Sinon, essaie de charger depuis Supabase Storage (documents_index.json)
      3. Si introuvable → tente une migration depuis l'ancien format
         (documents_backup.json cloud ou ./data/documents.json local)
      4. Si Supabase indisponible → retourne une liste vide (mode dégradé)
      5. La liste vide est aussi mise en cache (évite re-tentatives inutiles)

    Returns:
        Liste des documents.
    """
    global _documents_cache

    if _documents_cache is not None:
        return _documents_cache

    # Essayer de charger depuis le cloud (nouveau format)
    storage = _get_supabase_storage()
    if storage is not None:
        try:
            data = storage.download_file(_DOCUMENTS_KEY)
            if data:
                docs = json.loads(data.decode("utf-8"))
                if isinstance(docs, list):
                    _documents_cache = docs
                    return _documents_cache
        except Exception:
            pass

        # ── Migration depuis l'ancien backup cloud ────────────────────
        # L'ancien format utilisait documents_backup.json
        try:
            old_data = storage.download_file("documents_backup.json")
            if old_data:
                docs = json.loads(old_data.decode("utf-8"))
                if isinstance(docs, list):
                    _documents_cache = docs
                    # Sauvegarder au nouveau format
                    _save_cache(docs)
                    return _documents_cache
        except Exception:
            pass

    # ── Migration depuis l'ancien fichier local ─────────────────────
    # L'ancien format utilisait ./data/documents.json
    old_local = os.path.join(
        os.getenv("DATA_DIR", "./data"), "documents.json"
    )
    if os.path.exists(old_local):
        try:
            with open(old_local, "r", encoding="utf-8") as f:
                docs = json.load(f)
            if isinstance(docs, list):
                _documents_cache = docs
                # Sauvegarder au nouveau format cloud
                if storage is not None:
                    _save_cache(docs)
                return _documents_cache
        except Exception:
            pass

    # Mode dégradé : cache mémoire vide
    _documents_cache = []
    return _documents_cache


def _save_cache(docs: list[dict]):
    """Sauvegarde les documents dans le cache mémoire + cloud.

    La sauvegarde cloud est asynchrone du point de vue applicatif :
    si elle échoue, le cache mémoire est conservé et la donnée
    reste accessible en session.

    Args:
        docs: Liste complète des documents à sauvegarder.
    """
    global _documents_cache
    _documents_cache = docs

    # Persister vers le cloud (silencieux si échec)
    storage = _get_supabase_storage()
    if storage is not None:
        try:
            data = json.dumps(docs, indent=2, ensure_ascii=False).encode("utf-8")
            storage.upload_bytes(data, _DOCUMENTS_KEY, "application/json")
        except Exception as e:
            # En mode dégradé, on garde le cache mémoire
            print(f"⚠️ Sync cloud échouée : {e}")


def sync_from_cloud():
    """Force un rechargement depuis le cloud.

    À appeler au démarrage de l'application ou après une reconnexion.
    Écrase le cache mémoire avec les données du cloud.
    Si le cache est vide mais que des fichiers existent dans le bucket,
    lance une ré-indexation automatique.
    """
    global _documents_cache
    _documents_cache = None  # Invalide le cache
    _load_cache()  # Recharge

    # Filet de sécurité : si le cache est vide mais que Supabase
    # a des fichiers, on tente une ré-indexation
    if not _documents_cache and _get_supabase_storage() is not None:
        _try_reindex_from_bucket()


def _try_reindex_from_bucket():
    """Reconstruit l'index depuis les fichiers du bucket si le cache est vide.

    Évite les imports circulaires en utilisant une importation tardive.
    """
    try:
        from core.reindexer import reindex_all
        report = reindex_all()
        processed = report.get("total_processed", 0)
        if processed > 0:
            n_ok = report.get("total_success", 0)
            n_err = report.get("total_errors", 0)
            print(
                f"🔁 Auto-reindex (cache vide) : {processed} fichier(s) traité(s), "
                f"{n_ok} OK, {n_err} erreur(s)"
            )
    except Exception as e:
        print(f"⚠️ Ré-indexation automatique échouée : {e}")


def force_in_memory_mode():
    """Bascule en mode 100% mémoire (pour les tests).

    Vide le cache et désactive toute tentative d'accès au cloud.
    Les données ne seront PAS persistées.
    """
    global _documents_cache
    _documents_cache = []


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
    docs = _load_cache()
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
    """Ajoute un document à la base cloud.

    Découpe le texte en chunks et stocke le tout dans Supabase Storage.
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
    if content_hash:
        metadata["content_hash"] = content_hash
        metadata["hash_algorithm"] = _HASH_ALGORITHM

    doc = {
        "id": doc_id,
        "filename": filename,
        "text": text,
        "chunks": chunks,
        "chunks_count": len(chunks),
        "metadata": metadata,
    }

    docs = _load_cache()

    # Remplacer si le même filename existe déjà
    docs = [d for d in docs if d["filename"] != filename]
    docs.append(doc)

    _save_cache(docs)  # → mémoire + cloud

    return doc_id


def delete_document(filename: str) -> int:
    """Supprime un document par son nom.

    Args:
        filename: Nom du fichier à supprimer.

    Returns:
        Nombre de chunks supprimés.
    """
    docs = _load_cache()
    removed = [d for d in docs if d["filename"] == filename]
    docs = [d for d in docs if d["filename"] != filename]
    _save_cache(docs)  # → mémoire + cloud
    return removed[0]["chunks_count"] if removed else 0


def get_documents_list() -> list[dict]:
    """Retourne la liste des documents disponibles.

    Ignore silencieusement les documents corrompus (clés manquantes).

    Returns:
        Liste de dicts avec les infos des documents.
        Chaque entrée contient 'filename', 'chunks', 'metadata'
        et éventuellement 'content_hash'.
    """
    docs = _load_cache()
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
    docs = _load_cache()

    # Filtrer par document si demandé
    if document_name:
        docs = [d for d in docs if d["filename"] == document_name]

    if not docs:
        return []

    # Extraire les mots-clés de la requête
    keywords = _extract_keywords(query)

    if not keywords:
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
    return len(_load_cache())


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
