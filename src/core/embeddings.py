"""🧠 Génération d'embeddings vectoriels."""

import os
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

# ── Modèle par défaut ────────────────────────────────────────────────────
DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
_EMBEDDING_DIM = 384  # Dimension du modèle all-MiniLM-L6-v2


class EmbeddingGenerator:
    """Générateur d'embeddings pour les textes et les questions."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        """Initialise le générateur avec un modèle sentence-transformers.

        Args:
            model_name: Nom du modèle HuggingFace.
        """
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None

    @property
    def model(self) -> SentenceTransformer:
        """Charge le modèle au premier appel (lazy loading)."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dimension(self) -> int:
        """Dimension des vecteurs d'embedding produits."""
        return self.model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str]) -> np.ndarray:
        """Génère les embeddings pour une liste de textes.

        Args:
            texts: Liste de textes à encoder.

        Returns:
            Tableau numpy de forme (n_texts, dimension).
        """
        if not texts:
            return np.array([], dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings

    def encode_query(self, query: str) -> np.ndarray:
        """Génère l'embedding pour une question utilisateur.

        Args:
            query: Texte de la question.

        Returns:
            Vecteur d'embedding.
        """
        return self.encode([query])[0]


# ── Singleton global ─────────────────────────────────────────────────────
_global_embedder: Optional[EmbeddingGenerator] = None


def get_embedder() -> EmbeddingGenerator:
    """Retourne l'instance globale du générateur d'embeddings."""
    global _global_embedder
    if _global_embedder is None:
        _global_embedder = EmbeddingGenerator()
    return _global_embedder