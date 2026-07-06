"""💾 Base vectorielle ChromaDB pour la recherche sémantique."""

import os
import uuid
from typing import Optional

import chromadb
from chromadb.config import Settings

from core.embeddings import EmbeddingGenerator

# ── Configuration ────────────────────────────────────────────────────────
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME = "elearnbot_documents"


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
        except ValueError:
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
                    }
                seen[fname]["chunks"] += 1

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
        _global_vector_store = VectorStore()
    return _global_vector_store