"""Embedding implementations for generating vector representations of text."""

from functools import cached_property, lru_cache

import numpy as np
from numpy.typing import NDArray

from commonplace._logging import logger
from commonplace._search._types import Embedder

_ALIASES = {
    # Six layers to bge-small-en-v1.5's twelve, so about twice as fast, at much the same retrieval quality.
    "default": "fastembed:snowflake/snowflake-arctic-embed-xs",
}


@lru_cache(maxsize=8)
def get_embedder(model: str = "default") -> Embedder:
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
        logger.debug(f"Resolved embedder '{model}' to '{_ALIASES[model]}'")
        model = _ALIASES[model]

    try:
        if model.startswith("fastembed:"):
            model_name = model.split(":")[1]
            return FastEmbedEmbedder(model_name=model_name)
        if model.startswith("sentence-transformers:"):
            model_name = model.split(":", 1)[1]
            return SentenceTransformersEmbedder(model_name=model_name)
        elif model.startswith("llm:"):
            model_id = model.split(":", 1)[1]
            return LLMEmbedder(model_id=model_id)
        else:
            raise ValueError(f"Unsupported embedder model: {model}")
    except Exception as e:
        raise RuntimeError(f"Could not initialize embedder '{model}' : {e}") from e


#: What each model we've used was trained to see before a short retrieval query; documents go bare.
#: fastembed's `query_embed` adds nothing for these, so it falls to us, and a model not listed is refused
#: rather than guessed at. Sources: arctic declares it as `prompts.query` in its
#: `config_sentence_transformers.json`, which fastembed's ONNX copy leaves out; bge v1.5 gives it in the
#: BAAI model card, as optional but recommended.
_QUERY_INSTRUCTIONS = {
    "BAAI/bge-small-en-v1.5": "Represent this sentence for searching relevant passages: ",
    "snowflake/snowflake-arctic-embed-xs": "Represent this sentence for searching relevant passages: ",
}


class FastEmbedEmbedder:
    """Embedder using fastembed"""

    def __init__(self, model_name: str):
        if model_name not in _QUERY_INSTRUCTIONS:
            raise ValueError(
                f"No query instruction recorded for '{model_name}': add its prompts from the model card"
                " to _QUERY_INSTRUCTIONS"
            )
        self._model_name = model_name

    @cached_property
    def model(self):
        """Lazily load the sentence transformer model."""
        logger.info(f"Loading fastembed model '{self._model_name}'...")
        from fastembed import TextEmbedding

        return TextEmbedding(self._model_name)

    @property
    def model_id(self) -> str:
        """Get the model identifier."""
        return f"fastembed:{self._model_name}"

    def embed_doc(self, text: str) -> NDArray[np.float32]:
        """Generate an embedding for a document chunk."""
        return self.embed_docs([text])[0]

    def embed_query(self, text: str) -> NDArray[np.float32]:
        """Generate an embedding for a search query."""
        return next(iter(self.model.embed(_QUERY_INSTRUCTIONS[self._model_name] + text)))

    def embed_docs(self, texts: list[str]) -> NDArray[np.float32]:
        """Generate embeddings for multiple document chunks."""
        embeddings = self.model.embed(texts)
        return np.stack([e for e in embeddings])


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
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        return SentenceTransformer(self._model_name)

    @property
    def model_id(self) -> str:
        """Get the model identifier."""
        return self._model_id

    def embed_doc(self, text: str) -> NDArray[np.float32]:
        """Generate an embedding for a document chunk."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)

    def embed_query(self, text: str) -> NDArray[np.float32]:
        """Generate an embedding for a search query."""
        return self.embed_doc(text)

    def embed_docs(self, texts: list[str]) -> NDArray[np.float32]:
        """Generate embeddings for multiple document chunks."""
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

    def embed_doc(self, text: str) -> NDArray[np.float32]:
        """Generate an embedding for a document chunk."""
        embedding = self.model.embed(text)
        return np.array(embedding, dtype=np.float32)

    def embed_query(self, text: str) -> NDArray[np.float32]:
        """Generate an embedding for a search query."""
        return self.embed_doc(text)

    def embed_docs(self, texts: list[str]) -> NDArray[np.float32]:
        """Generate embeddings for multiple document chunks."""
        embeddings = [self.model.embed(text) for text in texts]
        return np.array(embeddings, dtype=np.float32)
