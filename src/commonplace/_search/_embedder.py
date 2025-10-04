"""Embedding implementations for generating vector representations of text."""

import numpy as np
from numpy.typing import NDArray


class SentenceTransformersEmbedder:
    """
    Embedder using sentence-transformers models.

    Downloads models to a configurable cache directory and generates
    embeddings locally without network access.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the embedder.

        Args:
            model_name: Name of the sentence-transformers model to use
        """
        # Lazy import to avoid loading heavy dependencies at module import time
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self._model_id = f"sentence-transformers:{model_name}"

    @property
    def model_id(self) -> str:
        """Get the model identifier."""
        return self._model_id

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


class LLMEmbedder:
    """
    Embedder using LLM's embedding models.

    Uses the llm library to generate embeddings via various providers
    (OpenAI, Gemini, etc.) configured through llm's settings.
    """

    def __init__(self, model_id: str = "3-small"):
        """
        Initialize the embedder.

        Args:
            model_id: LLM model ID for embeddings (e.g., "3-small", "3-large")
        """
        # Lazy import to avoid loading at module import time
        import llm

        self.model = llm.get_embedding_model(model_id)
        self._model_id = f"llm:{model_id}"

    @property
    def model_id(self) -> str:
        """Get the model identifier."""
        return self._model_id

    def embed(self, text: str) -> NDArray[np.float32]:
        """
        Generate an embedding for a single text.

        Args:
            text: The text to embed

        Returns:
            Embedding vector
        """
        embedding = self.model.embed(text)
        return np.array(embedding, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> NDArray[np.float32]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embedding vectors, shape (len(texts), embedding_dim)
        """
        embeddings = [self.model.embed(text) for text in texts]
        return np.array(embeddings, dtype=np.float32)
