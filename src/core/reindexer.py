"""🔄 Ré-indexation automatique des cours.

Maintient la synchronisation entre le stockage cloud (Supabase Storage)
et l'index local (documents.json). Détecte automatiquement :

- **Nouveaux fichiers** dans Supabase → les indexe
- **Fichiers modifiés** (hash différent) → ré-indexe
- **Fichiers supprimés** de Supabase → optionnel, les marque ou supprime

Fonctionne au démarrage de l'application et via un déclencheur manuel.
"""

import os
import io
import logging
from datetime import datetime
from typing import Optional

from core import document_store
from core.document_store import (
    compute_content_hash,
    get_document_by_filename,
    add_document,
    get_documents_list,
)

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger("reindexer")

# ── Types ─────────────────────────────────────────────────────────────────
SyncStatus = dict
"""
Dict représentant l'état de synchronisation :
{
    "total_in_supabase": int,
    "total_indexed": int,
    "new_files": [{"name": str, "size": int, "updated_at": str}, ...],
    "modified_files": [{"name": str, "old_hash": str, "new_hash": str}, ...],
    "missing_files": [str, ...],  # dans l'index mais plus dans Supabase
    "synced_files": [str, ...],   # OK, pas de changement
    "last_checked": str (ISO timestamp),
}
"""

ReindexReport = dict
"""
Rapport d'une opération de ré-indexation :
{
    "started_at": str,
    "completed_at": str,
    "duration_ms": int,
    "indexed": [str, ...],     # fichiers nouvellement indexés
    "updated": [str, ...],     # fichiers mis à jour (hash changé)
    "skipped": [str, ...],     # fichiers déjà à jour
    "errors": [{"file": str, "error": str}, ...],
    "total_processed": int,
    "total_success": int,
    "total_errors": int,
}
"""


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_supabase_storage():
    """Retourne l'instance SupabaseStorage ou None."""
    try:
        from integrations.supabase_storage import SupabaseStorage
        return SupabaseStorage()
    except Exception as e:
        logger.warning(f"Supabase non disponible : {e}")
        return None


def _classify_file(filename: str) -> str:
    """Détecte le type de fichier à partir de son extension.

    Returns:
        "pdf", "mp4", ou "unknown".
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return "pdf"
    elif ext == "mp4":
        return "mp4"
    return "unknown"


def _is_supported_type(filename: str) -> bool:
    """Vérifie si le fichier peut être indexé (PDF ou MP4)."""
    return _classify_file(filename) in ("pdf", "mp4")


# ── Scan des fichiers Supabase ─────────────────────────────────────────────

def scan_supabase_files() -> list[dict]:
    """Liste tous les fichiers dans le bucket Supabase Storage.

    Returns:
        Liste de dicts avec les clés 'name', 'size', 'updated_at', 'id'.
        Vide si Supabase n'est pas configuré ou si le bucket est vide.
    """
    storage = _get_supabase_storage()
    if storage is None:
        return []

    try:
        files = storage.list_files()
        # Filtrer pour ne garder que les fichiers indexables
        supported = []
        for f in files:
            name = f.get("name", "")
            if _is_supported_type(name):
                supported.append({
                    "name": name,
                    "size": f.get("size", 0) or f.get("metadata", {}).get("size", 0),
                    "updated_at": f.get("updated_at", f.get("created_at", "")),
                    "id": f.get("id", name),
                })
        return supported
    except Exception as e:
        logger.error(f"Erreur scan Supabase : {e}")
        return []


def get_storage_file_hash(filename: str) -> Optional[str]:
    """Télécharge un fichier depuis Supabase et calcule son hash SHA256.

    Args:
        filename: Nom du fichier dans le bucket.

    Returns:
        Hash hexadécimal SHA256, ou None si erreur.
    """
    storage = _get_supabase_storage()
    if storage is None:
        return None

    try:
        file_bytes = storage.download_file(filename)
        if file_bytes:
            return compute_content_hash(file_bytes)
        return None
    except Exception as e:
        logger.error(f"Erreur hash pour {filename} : {e}")
        return None


# ── Vérification de synchronisation ────────────────────────────────────────

def check_sync_status() -> SyncStatus:
    """Compare l'index local avec les fichiers dans Supabase Storage.

    Identifie les fichiers nouveaux, modifiés, supprimés et synchronisés.

    Returns:
        SyncStatus dict avec l'état complet de la synchronisation.
    """
    supabase_files = scan_supabase_files()
    indexed_docs = get_documents_list()

    # Index des docs locaux par nom de fichier
    indexed_by_name = {d["filename"]: d for d in indexed_docs}

    # Index des fichiers Supabase par nom
    supabase_by_name = {f["name"]: f for f in supabase_files}

    new_files = []
    modified_files = []
    synced_files = []
    missing_files = []

    # ── Fichiers dans Supabase ─────────────────────────────────────────
    for sf in supabase_files:
        name = sf["name"]
        if name not in indexed_by_name:
            # Nouveau fichier : pas encore indexé
            new_files.append(sf)
        else:
            # Fichier déjà indexé → vérifier le hash
            local_doc = indexed_by_name[name]
            local_hash = local_doc.get("content_hash") or \
                local_doc.get("metadata", {}).get("content_hash")

            if local_hash:
                # Vérifier si le hash remote a changé
                remote_hash = get_storage_file_hash(name)
                if remote_hash and remote_hash != local_hash:
                    modified_files.append({
                        "name": name,
                        "old_hash": local_hash,
                        "new_hash": remote_hash,
                    })
                else:
                    synced_files.append(name)
            else:
                # Pas de hash stocké → considéré comme nouveau
                # (cela arrive pour les documents indexés avant l'ajout du hash)
                new_files.append(sf)

    # ── Fichiers dans l'index mais plus dans Supabase ──────────────────
    for fname in indexed_by_name:
        if fname not in supabase_by_name:
            missing_files.append(fname)

    return {
        "total_in_supabase": len(supabase_files),
        "total_indexed": len(indexed_docs),
        "new_files": new_files,
        "modified_files": modified_files,
        "missing_files": missing_files,
        "synced_files": synced_files,
        "last_checked": datetime.utcnow().isoformat(),
    }


# ── Ré-indexation ─────────────────────────────────────────────────────────

def reindex_file(filename: str) -> dict:
    """Ré-indexe un fichier depuis Supabase Storage.

    Télécharge le fichier, extrait le texte, recalcule le hash,
    et met à jour l'index local.

    Args:
        filename: Nom du fichier à ré-indexer.

    Returns:
        Dict avec "success" (bool), "action" ("indexed"|"updated"),
        "filename" (str), et optionnellement "error" (str).
    """
    storage = _get_supabase_storage()
    if storage is None:
        return {
            "success": False,
            "filename": filename,
            "error": "Supabase Storage non configuré",
        }

    try:
        # 1. Télécharger le fichier
        file_bytes = storage.download_file(filename)
        if not file_bytes:
            return {
                "success": False,
                "filename": filename,
                "error": "Fichier introuvable dans Supabase",
            }

        # 2. Calculer le hash du contenu
        content_hash = compute_content_hash(file_bytes)

        # 3. Vérifier si déjà indexé avec le même hash
        existing = get_document_by_filename(filename)
        if existing:
            existing_hash = existing.get("metadata", {}).get("content_hash")
            if existing_hash and existing_hash == content_hash:
                return {
                    "success": True,
                    "action": "skipped",
                    "filename": filename,
                    "message": "Déjà à jour",
                }

        # 4. Extraire le texte selon le type
        content_type = _classify_file(filename)
        text = ""
        metadata = {}

        if content_type == "pdf":
            from core.pdf_extractor import extract_text_from_bytes
            text = extract_text_from_bytes(file_bytes)
            metadata = {
                "content_type": "pdf",
                "size": len(file_bytes),
            }
        elif content_type == "mp4":
            from core.video_processor import process_video
            # Sauvegarder temporairement pour traitement
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            try:
                result = process_video(tmp_path, language="fr")
                text = result.get("text", "")
                duration = result.get("duration", 0)
                mins, secs = divmod(int(duration), 60)
                metadata = {
                    "content_type": "mp4",
                    "size": len(file_bytes),
                    "duration": duration,
                    "duration_display": f"{mins}:{secs:02d}",
                    "language": result.get("language", "fr"),
                }
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        if not text.strip():
            return {
                "success": False,
                "filename": filename,
                "error": f"Texte vide après extraction ({content_type})",
            }

        # 5. Indexer ou mettre à jour
        action = "updated" if existing else "indexed"
        add_document(
            text=text,
            filename=filename,
            metadata=metadata,
            content_hash=content_hash,
        )

        return {
            "success": True,
            "action": action,
            "filename": filename,
            "chunks": len(text.split()) // 500 + 1,
        }

    except Exception as e:
        logger.exception(f"Erreur ré-indexation {filename}")
        return {
            "success": False,
            "filename": filename,
            "error": str(e),
        }


def reindex_all(filenames: list[str] = None) -> ReindexReport:
    """Ré-indexe plusieurs fichiers depuis Supabase Storage.

    Args:
        filenames: Liste des noms de fichiers à ré-indexer.
                   Si None, ré-indexe tout ce qui n'est pas à jour.

    Returns:
        ReindexReport détaillant l'opération.
    """
    started_at = datetime.utcnow()

    # Déterminer les fichiers à traiter
    if filenames is None:
        status = check_sync_status()
        filenames = (
            [f["name"] for f in status["new_files"]]
            + [f["name"] for f in status["modified_files"]]
        )
        # Ajouter les fichiers sans hash (anciens docs)
        for d in get_documents_list():
            if not d.get("content_hash") and d["filename"] not in filenames:
                filenames.append(d["filename"])

    if not filenames:
        return {
            "started_at": started_at.isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": 0,
            "indexed": [],
            "updated": [],
            "skipped": [],
            "errors": [],
            "total_processed": 0,
            "total_success": 0,
            "total_errors": 0,
            "message": "Tout est déjà à jour",
        }

    # Traiter chaque fichier
    indexed = []
    updated = []
    skipped = []
    errors = []

    for fname in filenames:
        result = reindex_file(fname)
        if result["success"]:
            action = result.get("action", "indexed")
            if action == "indexed":
                indexed.append(fname)
            elif action == "updated":
                updated.append(fname)
            else:
                skipped.append(fname)
        else:
            errors.append({"file": fname, "error": result.get("error", "?")})

    completed_at = datetime.utcnow()
    duration = (completed_at - started_at).total_seconds() * 1000

    return {
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": int(duration),
        "indexed": indexed,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_processed": len(filenames),
        "total_success": len(indexed) + len(updated) + len(skipped),
        "total_errors": len(errors),
    }


def auto_reindex_on_startup() -> ReindexReport:
    """Lancé au démarrage de l'application.

    Vérifie si des fichiers doivent être ré-indexés et procède
    automatiquement. Silencieux si tout est à jour.

    Returns:
        ReindexReport de l'opération.
    """
    # Vérifier si Supabase est configuré
    storage = _get_supabase_storage()
    if storage is None:
        return {
            "message": "Supabase non configuré — ré-indexation automatique désactivée",
            "total_processed": 0,
            "total_success": 0,
            "total_errors": 0,
        }

    report = reindex_all()

    if report["total_processed"] > 0:
        logger.info(
            f"Auto-reindex : {len(report['indexed'])} nouveau(x), "
            f"{len(report['updated'])} mis à jour, "
            f"{len(report['errors'])} erreur(s)"
        )

    return report


# ── Utilitaires d'affichage ────────────────────────────────────────────────

def format_sync_summary(status: SyncStatus) -> str:
    """Formate un résumé lisible de l'état de synchronisation.

    Args:
        status: SyncStatus retourné par check_sync_status().

    Returns:
        Chaîne formatée pour affichage.
    """
    parts = [
        f"☁️ {status['total_in_supabase']} fichier(s) dans Supabase",
        f"📚 {status['total_indexed']} document(s) indexés localement",
    ]

    if status["new_files"]:
        parts.append(f"🆕 {len(status['new_files'])} nouveau(x) à indexer")
    if status["modified_files"]:
        parts.append(f"🔄 {len(status['modified_files'])} fichier(s) modifié(s)")
    if status["missing_files"]:
        parts.append(f"🗑️ {len(status['missing_files'])} fichier(s) manquant(s) dans Supabase")
    if status["synced_files"]:
        parts.append(f"✅ {len(status['synced_files'])} fichier(s) à jour")

    return " · ".join(parts)
