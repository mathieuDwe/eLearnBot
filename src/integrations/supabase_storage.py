"""☁️ Intégration Supabase Storage pour le stockage des cours."""

import os
import io
from typing import Optional

from supabase import create_client, Client


# ── Configuration ────────────────────────────────────────────────────────
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
_BUCKET_NAME = "cours"

# Nettoyer l'URL (enlever /rest/v1/ si présent)
if _SUPABASE_URL.endswith("/rest/v1/"):
    _SUPABASE_URL = _SUPABASE_URL[: -len("/rest/v1/")]

# Cache du client (persistance de connexion)
_client_cache: Optional[Client] = None


def check_supabase_health() -> dict:
    """Vérifie la connexion Supabase et l'existence du bucket.

    Returns:
        Dict avec les clés 'supabase' (bool), 'bucket' (bool),
        'bucket_name' (str), 'error' (str|None).
    """
    result = {
        "supabase": False,
        "bucket": False,
        "bucket_name": _BUCKET_NAME,
        "error": None,
        "files_count": 0,
    }

    if not _SUPABASE_URL or not _SUPABASE_KEY:
        result["error"] = "SUPABASE_URL ou SUPABASE_KEY non définis"
        return result

    try:
        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        # Tester la connexion : lister le contenu du bucket 'cours'
        bucket_ref = client.storage.from_(_BUCKET_NAME)
        files = bucket_ref.list()
        result["supabase"] = True
        result["bucket"] = True
        if isinstance(files, list):
            result["files_count"] = len(files)

    except Exception as e:
        err_str = str(e)
        if "bucket" in err_str.lower() or "not found" in err_str.lower() or "404" in err_str:
            result["supabase"] = True  # Supabase fonctionne
            result["bucket"] = False
            result["error"] = f"Bucket '{_BUCKET_NAME}' introuvable"
        else:
            result["error"] = err_str[:80]

    return result


class SupabaseStorage:
    """Client pour stocker les fichiers dans Supabase Storage."""

    def __init__(self):
        """Initialise le client Supabase.

        Le client est créé une seule fois et réutilisé (singleton).

        Raises:
            ValueError: Si SUPABASE_URL ou SUPABASE_KEY ne sont pas configurés.
        """
        if not _SUPABASE_URL or not _SUPABASE_KEY:
            raise ValueError(
                "Supabase non configuré. "
                "Définissez SUPABASE_URL et SUPABASE_KEY dans .env"
            )

        global _client_cache
        if _client_cache is None:
            _client_cache = create_client(_SUPABASE_URL, _SUPABASE_KEY)

        self.client: Client = _client_cache
        self.bucket = self.client.storage.from_(_BUCKET_NAME)

    def upload_file(
        self,
        file_path: str,
        filename: str,
        content_type: str = "application/pdf",
    ) -> str:
        """Upload un fichier vers Supabase Storage et retourne l'URL publique.

        Note : Supabase n'accepte que certains MIME types.
        On utilise toujours application/pdf (le fichier reste correctement
        stocké, seul le header HTTP de content-type change).

        Args:
            file_path: Chemin local du fichier à uploader.
            filename: Nom du fichier sur Supabase (chemin complet).
            content_type: Type MIME (non utilisé, laissé pour compatibilité).

        Returns:
            URL publique du fichier stocké.

        Raises:
            Exception: Si l'upload échoue.
        """
        with open(file_path, "rb") as f:
            self.bucket.upload(
                path=filename,
                file=f,
                file_options={"content-type": "application/pdf"},
            )

        return self.bucket.get_public_url(filename)

    def delete_file(self, filename: str):
        """Supprime un fichier de Supabase Storage.

        Args:
            filename: Nom du fichier à supprimer.
        """
        self.bucket.remove(paths=[filename])

    def list_files(self) -> list[dict]:
        """Liste les fichiers dans le bucket.

        Returns:
            Liste des fichiers avec leurs métadonnées.
        """
        return self.bucket.list()

    def get_public_url(self, filename: str) -> str:
        """Retourne l'URL publique d'un fichier.

        Args:
            filename: Nom du fichier.

        Returns:
            URL publique.
        """
        return self.bucket.get_public_url(filename)

    def download_file(self, filename: str) -> Optional[bytes]:
        """Télécharge un fichier depuis Supabase Storage.

        Args:
            filename: Nom du fichier à télécharger.

        Returns:
            Contenu du fichier en bytes, ou None si introuvable.
        """
        try:
            res = self.bucket.download(path=filename)
            return res
        except Exception:
            return None

    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        content_type: str = "application/pdf",
    ) -> str:
        """Upload des bytes vers Supabase Storage (sans fichier temporaire)."""
        self.bucket.upload(
            path=filename,
            file=data,
            file_options={"content-type": content_type},
        )
        return self.bucket.get_public_url(filename)