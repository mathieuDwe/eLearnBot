"""☁️ Intégration Google Drive pour le stockage des cours."""

import io
import json
import os
from typing import Optional

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# ── Scopes Google Drive ──────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# ── Configuration ────────────────────────────────────────────────────────
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")


class GoogleDriveClient:
    """Client pour interagir avec Google Drive API."""

    def __init__(self, folder_id: Optional[str] = None):
        """Initialise le client Google Drive.

        Args:
            folder_id: ID du dossier Drive (défaut: variable d'env).

        Raises:
            GoogleAuthError: Si l'authentification échoue.
        """
        self.folder_id = folder_id or DRIVE_FOLDER_ID
        self._service = None

    @property
    def service(self):
        """Initialise et retourne le service Drive (lazy)."""
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _build_service(self):
        """Construit le service Google Drive.

        Supporte deux modes :
        1. Fichier JSON de compte de service (local)
        2. Secret JSON Streamlit Cloud (GOOGLE_SERVICE_ACCOUNT_JSON)

        Returns:
            Service Google Drive.
        """
        # Essayer d'abord le secret Streamlit Cloud
        service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if service_account_json:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(service_account_json),
                scopes=SCOPES,
            )
            return build("drive", "v3", credentials=creds)

        # Fallback : fichier JSON local
        creds_path = os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS", "service_account.json"
        )
        if os.path.exists(creds_path):
            creds = service_account.Credentials.from_service_account_file(
                creds_path,
                scopes=SCOPES,
            )
            return build("drive", "v3", credentials=creds)

        raise GoogleAuthError(
            "Aucune configuration Google Drive trouvée. "
            "Configurez GOOGLE_SERVICE_ACCOUNT_JSON ou "
            "GOOGLE_APPLICATION_CREDENTIALS."
        )

    def upload_pdf(
        self,
        file_path: str,
        filename: str,
        mime_type: str = "application/pdf",
    ) -> str:
        """Upload un fichier PDF vers Google Drive.

        Args:
            file_path: Chemin local du fichier.
            filename: Nom du fichier sur Drive.
            mime_type: Type MIME du fichier.

        Returns:
            ID du fichier créé sur Drive.

        Raises:
            GoogleAuthError: Si l'authentification échoue.
        """
        # Vérifier si le fichier existe déjà
        existing_id = self._find_file(filename)
        if existing_id:
            # Mettre à jour le fichier existant
            media = MediaFileUpload(file_path, mimetype=mime_type)
            self.service.files().update(
                fileId=existing_id,
                media_body=media,
            ).execute()
            return existing_id

        # Créer un nouveau fichier
        file_metadata = {
            "name": filename,
            "parents": [self.folder_id] if self.folder_id else [],
        }
        media = MediaFileUpload(file_path, mimetype=mime_type)
        file = (
            self.service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        return file.get("id")

    def download_pdf(self, file_id: str) -> bytes:
        """Télécharge un fichier PDF depuis Google Drive.

        Args:
            file_id: ID du fichier sur Drive.

        Returns:
            Contenu du fichier en bytes.
        """
        request = self.service.files().get_media(fileId=file_id)
        file_bytes = io.BytesIO()
        downloader = MediaIoBaseDownload(file_bytes, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return file_bytes.getvalue()

    def list_pdfs(self) -> list[dict]:
        """Liste les fichiers PDF dans le dossier Drive configuré.

        Returns:
            Liste de dicts avec 'id', 'name', 'createdTime', 'size'.
        """
        query = (
            f"mimeType='application/pdf' "
            f"and '{self.folder_id}' in parents "
            f"and trashed=false"
        )
        results = (
            self.service.files()
            .list(
                q=query,
                fields="files(id, name, createdTime, size)",
                orderBy="createdTime desc",
            )
            .execute()
        )
        return results.get("files", [])

    def delete_file(self, file_id: str):
        """Supprime un fichier sur Google Drive.

        Args:
            file_id: ID du fichier à supprimer.
        """
        self.service.files().delete(fileId=file_id).execute()

    def _find_file(self, filename: str) -> Optional[str]:
        """Cherche un fichier par nom dans le dossier Drive.

        Args:
            filename: Nom du fichier à chercher.

        Returns:
            ID du fichier s'il existe, None sinon.
        """
        query = (
            f"name='{filename}' "
            f"and '{self.folder_id}' in parents "
            f"and trashed=false"
        )
        results = (
            self.service.files()
            .list(q=query, fields="files(id)")
            .execute()
        )
        files = results.get("files", [])
        return files[0]["id"] if files else None