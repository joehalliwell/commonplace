"""Embedding implementations for generating vector representations of text."""

from functools import cached_property, lru_cache

import numpy as np
from numpy.typing import NDArray

from commonplace import logger

_ALIASES = {
    "default": "sentence-transformers:all-MiniLM-L6-v2",
}


@lru_cache(maxsize=8)
def get_embedder(model: str = "default"):
    """
    Factory function to get an embedder instance based on a model identifier.

    Args:
        model: Model identifier string. Examples:
            - "sentence-transformers:all-MiniLM-L6-v2"
            - "llm:3-small"

    Returns:
        An embedder instance
    """
    if model in _ALIASES:
        logger.debug(f"Resolved embedder '{model}' -> '{_ALIASES[model]}'")
        model = _ALIASES[model]

    if model.startswith("sentence-transformers:"):
        model_name = model.split(":", 1)[1]
        return SentenceTransformersEmbedder(model_name=model_name)
    elif model.startswith("llm:"):
        model_id = model.split(":", 1)[1]
        return LLMEmbedder(model_id=model_id)
    else:
        raise ValueError(f"Unsupported embedder model: {model}")


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
        self._model_name = model_name
        self._model_id = f"sentence-transformers:{model_name}"

    @cached_property
    def model(self):
        """Lazily load the sentence transformer model."""
        logger.info(f"Loading sentence-transformers model '{self._model_name}'...")
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self._model_name)

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
