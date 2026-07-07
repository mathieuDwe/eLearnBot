"""💾 Base vectorielle ChromaDB pour la recherche sémantique."""

import io
import os
import uuid
import zipfile
from typing import Optional

import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError

from core.embeddings import EmbeddingGenerator

# ── Configuration ────────────────────────────────────────────────────────
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME = "elearnbot_documents"
CLOUD_BACKUP_KEY = "chroma_db_backup.zip"


def _get_supabase_storage() -> Optional[object]:
    """Retourne le bucket Supabase Storage pour les backups ChromaDB."""
    try:
        from integrations.supabase_storage import SupabaseStorage
        return SupabaseStorage()
    except Exception as e:
        print(f"ℹ️ Supabase Storage non disponible : {e}")
        return None


def _zip_chroma_db(persist_directory: str) -> bytes:
    """Compresse le dossier ChromaDB en zip.

    Args:
        persist_directory: Chemin du dossier ChromaDB.

    Returns:
        Contenu du zip en bytes.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(persist_directory):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, persist_directory)
                zf.write(file_path, arcname)
    return buf.getvalue()


def _unzip_chroma_db(zip_bytes: bytes, persist_directory: str):
    """Extrait un zip dans le dossier ChromaDB.

    Args:
        zip_bytes: Contenu du zip en bytes.
        persist_directory: Dossier de destination.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(persist_directory)


def load_chroma_from_cloud():
    """Télécharge et restaure ChromaDB depuis Supabase Storage.

    À appeler au démarrage de l'application.
    """
    storage = _get_supabase_storage()
    if storage is None:
        return

    try:
        zip_bytes = storage.download_file(CLOUD_BACKUP_KEY)
        if zip_bytes:
            os.makedirs(CHROMA_DB_PATH, exist_ok=True)
            _unzip_chroma_db(zip_bytes, CHROMA_DB_PATH)
            print(f"✅ ChromaDB restaurée depuis le cloud ({len(zip_bytes)} octets)")
    except Exception as e:
        print(f"ℹ️ Aucun backup ChromaDB trouvé dans le cloud : {e}")


def save_chroma_to_cloud():
    """Sauvegarde ChromaDB vers Supabase Storage.

    À appeler après chaque indexation de document.
    """
    storage = _get_supabase_storage()
    if storage is None:
        return

    if not os.path.exists(CHROMA_DB_PATH):
        return

    try:
        zip_bytes = _zip_chroma_db(CHROMA_DB_PATH)
        storage.upload_bytes(
            data=zip_bytes,
            filename=CLOUD_BACKUP_KEY,
            content_type="application/zip",
        )
        print(f"✅ ChromaDB sauvegardée dans le cloud ({len(zip_bytes)} octets)")
    except Exception as e:
        print(f"⚠️ Échec de la sauvegarde ChromaDB : {e}")


class VectorStore:
    """Interface vers ChromaDB pour stocker et rechercher des embeddings."""

    def __init__(
        self,
        persist_directory: str = CHROMA_DB_PATH,
        embedding_generator: Optional[EmbeddingGenerator] = None,
    ):
        """Initialise la connexion ChromaDB.

        Args:
            persist_directory: Chemin de persistence.
            embedding_generator: Générateur d'embeddings.
        """
        self.persist_directory = persist_directory
        self.embedder = embedding_generator or EmbeddingGenerator()

        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

        # Créer ou récupérer la collection
        try:
            self.collection = self.client.get_collection(COLLECTION_NAME)
        except NotFoundError:
            self.collection = self.client.create_collection(
                COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )

    def add_document(
        self,
        chunks: list[str],
        filename: str,
        metadata: Optional[dict] = None,
    ) -> list[str]:
        """Ajoute les chunks d'un document à la base vectorielle.

        Args:
            chunks: Liste de chunks de texte.
            filename: Nom du fichier source.
            metadata: Métadonnées additionnelles.

        Returns:
            Liste des IDs des chunks insérés.
        """
        if not chunks:
            return []

        metadata = metadata or {}
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [
            {
                "filename": filename,
                "chunk_index": i,
                "total_chunks": len(chunks),
                **metadata,
            }
            for i in range(len(chunks))
        ]

        self.collection.add(
            documents=chunks,
            metadatas=metadatas,
            ids=ids,
        )

        # Persister vers le cloud après chaque ajout
        save_chroma_to_cloud()

        return ids

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_dict: Optional[dict] = None,
    ) -> list[dict]:
        """Recherche les chunks les plus similaires à une requête.

        Args:
            query: Texte de la requête.
            n_results: Nombre de résultats à retourner.
            filter_dict: Filtre optionnel (ex: {"filename": "cours.pdf"}).

        Returns:
            Liste de dicts avec 'text', 'score', 'metadata'.
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=filter_dict,
        )

        documents = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                documents.append({
                    "text": doc,
                    "score": results["distances"][0][i]
                    if results["distances"]
                    else 0.0,
                    "metadata": results["metadatas"][0][i]
                    if results["metadatas"]
                    else {},
                })

        return documents

    def get_documents_list(self) -> list[dict]:
        """Retourne la liste des documents disponibles.

        Returns:
            Liste de dicts avec filename et metadata.
        """
        # Récupérer un échantillon pour déduire la liste des documents
        results = self.collection.get(limit=1000)

        seen = {}
        if results["metadatas"]:
            for meta in results["metadatas"]:
                fname = meta.get("filename", "inconnu")
                if fname not in seen:
                    seen[fname] = {
                        "filename": fname,
                        "chunks": 0,
                        "metadata": {},
                    }
                seen[fname]["chunks"] += 1
                # Garder les métadonnées du premier chunk
                if not seen[fname]["metadata"]:
                    seen[fname]["metadata"] = {
                        k: v for k, v in meta.items()
                        if k not in ("filename", "chunk_index", "total_chunks")
                    }

        return list(seen.values())

    def delete_document(self, filename: str) -> int:
        """Supprime tous les chunks d'un document.

        Args:
            filename: Nom du fichier à supprimer.

        Returns:
            Nombre de chunks supprimés.
        """
        results = self.collection.get(
            where={"filename": filename},
        )
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            # Persister vers le cloud après suppression
            save_chroma_to_cloud()
        return len(results["ids"])

    def count_documents(self) -> int:
        """Retourne le nombre total de documents indexés."""
        return self.collection.count()


# ── Singleton global ─────────────────────────────────────────────────────
_global_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Retourne l'instance globale du vector store."""
    global _global_vector_store
    if _global_vector_store is None:
        # Essayer de restaurer depuis le cloud (Streamlit Cloud)
        load_chroma_from_cloud()
        _global_vector_store = VectorStore()
    return _global_vector_store