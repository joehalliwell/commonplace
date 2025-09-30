"""Embedding implementations for generating vector representations of text."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray


class SentenceTransformersEmbedder:
    """
    Embedder using sentence-transformers models.

    Downloads models to a configurable cache directory and generates
    embeddings locally without network access.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", cache_dir: Path | None = None):
        """
        Initialize the embedder.

        Args:
            model_name: Name of the sentence-transformers model to use
            cache_dir: Optional directory to cache models (defaults to ~/.cache/torch)
        """
        # Lazy import to avoid loading heavy dependencies at module import time
        from sentence_transformers import SentenceTransformer

        cache_path = str(cache_dir) if cache_dir else None
        self.model = SentenceTransformer(model_name, cache_folder=cache_path)

    def embed(self, text: str) -> NDArray[np.float32]:
        """
        Generate an embedding for a single text.

        Args:
            text: The text to embed

        Returns:
            Embedding vector
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)

    def embed_batch(self, texts: list[str]) -> NDArray[np.float32]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embedding vectors, shape (len(texts), embedding_dim)
        """
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.astype(np.float32)
