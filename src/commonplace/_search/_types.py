"""
Type definitions and protocols for semantic search.

This module defines the core abstractions for chunking notes,
generating embeddings, and storing/searching vectors.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Iterator, Protocol

import numpy as np
from numpy.typing import NDArray

from commonplace._types import Note, RepoPath


class SearchMethod(str, Enum):
    """Search method for finding relevant chunks."""

    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


@dataclass
class Chunk:
    """A chunk of text extracted from a note."""

    repo_path: RepoPath
    """Repository path to the source note"""

    text: str
    """The chunk text content"""

    section: str
    """Section path (e.g. 'Meeting Notes / Action Items')"""

    offset: int
    """Character offset in source"""


@dataclass
class SearchHit:
    """A chunk with a similarity score."""

    chunk: Chunk
    score: float
    """Similarity score (higher is more similar)"""


class Chunker(Protocol):
    """Protocol for chunking notes into smaller pieces."""

    def chunk(self, note: Note) -> Iterator[Chunk]:
        """
        Split a note into chunks.

        Args:
            note: The note to chunk

        Yields:
            Chunks extracted from the note
        """
        ...


class Embedder(Protocol):
    """Protocol for generating embeddings from text."""

    @property
    def model_id(self) -> str:
        """
        Get the model identifier.

        Returns:
            Model ID string used to track which model generated embeddings
        """
        ...

    def embed(self, text: str) -> NDArray[np.float32]:
        """
        Generate an embedding for a single text.

        Args:
            text: The text to embed

        Returns:
            Embedding vector
        """
        ...

    def embed_batch(self, texts: list[str]) -> NDArray[np.float32]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embedding vectors, shape (len(texts), embedding_dim)
        """
        ...


@dataclass
class IndexStat:
    """Statistic about a particular set of chunks"""

    model_id: str
    repo_path: RepoPath
    num_chunks: int


class SearchIndex(Protocol):
    """Protocol for storing and searching embeddings."""

    def add_chunk(self, chunk: Chunk) -> None:
        """
        Add a chunk of text to the store.

        Args:
            chunk: The chunk to store
            embedding: The chunk's embedding vector
        """
        ...

    def get_indexed_paths(self) -> Iterable[RepoPath]:
        """
        Paths that have been indexed.
        """
        ...

    def search(self, query: str, limit: int = 10, method: SearchMethod = SearchMethod.HYBRID) -> list[SearchHit]:
        """
        Search for similar chunks.

        Args:
            query_embedding: The query embedding vector
            limit: Maximum number of results to return

        Returns:
            List of search hits, ordered by descending similarity
        """
        ...

    def clear(self) -> None:
        """Remove all chunks from the store."""
        ...

    def stats(self) -> Iterator[IndexStat]:
        """Get stats on this index"""
        ...
