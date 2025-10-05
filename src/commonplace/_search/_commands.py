"""Semantic search components for commonplace."""

from pathlib import Path

from commonplace import logger
from commonplace._repo import Commonplace
from commonplace._search._chunker import MarkdownChunker
from commonplace._search._embedder import (
    LLMEmbedder as LLMEmbedder,
    SentenceTransformersEmbedder as SentenceTransformersEmbedder,
)
from commonplace._search._store import SQLiteVectorStore
from commonplace._search._types import (
    Embedder,
    SearchHit as SearchHit,
    SearchMethod as SearchMethod,
)
from commonplace._utils import progress_track


def index(
    repo: Commonplace,
    db_path: Path,
    rebuild: bool = False,
    batch_size: int = 100,
    model_id: str = "3-small",
    embedder: Embedder | None = None,
) -> None:
    """
    Build or rebuild the search index for semantic search.

    Args:
        repo: The commonplace repository to index
        db_path: Path to the SQLite database file for the index
        rebuild: If True, clear existing index before rebuilding
        batch_size: Number of chunks to embed at once
        model_id: LLM model ID for embeddings (default: "3-small")
        embedder: Optional embedder instance (if None, uses LLMEmbedder with model_id)
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if embedder is None:
        embedder = SentenceTransformersEmbedder()
    store = SQLiteVectorStore(db_path, embedder=embedder)
    chunker = MarkdownChunker()

    if rebuild:
        logger.info("Clearing existing index")
        store.clear()

    # Collect notes to index
    all_notes = list(repo.notes())
    if rebuild:
        notes_to_index = all_notes
    else:
        # Check which notes need indexing based on (path, ref, model) tuples
        indexed_refs = store.get_indexed_paths()
        notes_to_index = []

        for note in all_notes:
            path_str = str(note.repo_path.path)
            indexed_at = indexed_refs.get(path_str, set())

            if note.repo_path.ref not in indexed_at:
                # This (path, ref) pair hasn't been indexed with this model
                notes_to_index.append(note)

        if notes_to_index:
            logger.info(
                f"Found {len(notes_to_index)} notes to index with {embedder.model_id} (out of {len(all_notes)} total)"
            )
        else:
            logger.info(f"All {len(all_notes)} notes are already indexed with {embedder.model_id}")
            store.close()
            return

    logger.info(f"Chunking {len(notes_to_index)} notes")

    all_chunks = []
    for note in progress_track(notes_to_index, "Chunking notes"):
        logger.debug(f"Chunking {note.repo_path}")
        chunks = list(chunker.chunk(note))
        all_chunks.extend(chunks)

    logger.info(f"Embedding {len(all_chunks)} chunks with {embedder.model_id} in batches of {batch_size}")

    # Process chunks in batches
    num_batches = (len(all_chunks) + batch_size - 1) // batch_size
    for i in progress_track(range(0, len(all_chunks), batch_size), "Embedding chunks", total=num_batches):
        batch = all_chunks[i : i + batch_size]
        texts = [chunk.text for chunk in batch]
        embeddings = embedder.embed_batch(texts)

        # Store each chunk with its embedding
        for chunk, embedding in zip(batch, embeddings):
            store._add_with_embedding(chunk, embedding)

    store.close()
    logger.info("Indexing complete")
