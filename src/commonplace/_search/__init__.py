"""Semantic search components for commonplace."""

from pathlib import Path

from commonplace import logger
from commonplace._repo import Commonplace
from commonplace._search._chunker import MarkdownChunker
from commonplace._search._embedder import SentenceTransformersEmbedder
from commonplace._search._store import SQLiteVectorStore
from commonplace._search._types import SearchHit
from commonplace._utils import progress_track


def index(
    repo: Commonplace,
    db_path: Path,
    rebuild: bool = False,
    batch_size: int = 100,
) -> None:
    """
    Build or rebuild the search index for semantic search.

    Args:
        repo: The commonplace repository to index
        db_path: Path to the SQLite database file for the index
        rebuild: If True, clear existing index before rebuilding
        batch_size: Number of chunks to embed at once
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    store = SQLiteVectorStore(db_path)
    chunker = MarkdownChunker()
    embedder = SentenceTransformersEmbedder()

    if rebuild:
        logger.info("Clearing existing index")
        store.clear()

    # Collect notes to index
    all_notes = list(repo.notes())
    if rebuild:
        notes_to_index = all_notes
    else:
        indexed_paths = store.get_indexed_paths()
        notes_to_index = [note for note in all_notes if str(note.path) not in indexed_paths]
        if notes_to_index:
            logger.info(f"Found {len(notes_to_index)} new notes to index (out of {len(all_notes)} total)")
        else:
            logger.info(f"All {len(all_notes)} notes are already indexed")
            store.close()
            return

    logger.info(f"Chunking {len(notes_to_index)} notes")

    all_chunks = []
    for note in progress_track(notes_to_index, "Chunking notes"):
        chunks = list(chunker.chunk(note))
        all_chunks.extend(chunks)

    logger.info(f"Embedding {len(all_chunks)} chunks in batches of {batch_size}")

    # Process chunks in batches
    num_batches = (len(all_chunks) + batch_size - 1) // batch_size
    for i in progress_track(range(0, len(all_chunks), batch_size), "Embedding chunks", total=num_batches):
        batch = all_chunks[i : i + batch_size]
        texts = [chunk.text for chunk in batch]
        embeddings = embedder.embed_batch(texts)

        # Store each chunk with its embedding
        for chunk, embedding in zip(batch, embeddings):
            store.add(chunk, embedding)

    store.close()
    logger.info("Indexing complete")


def search(
    db_path: Path,
    query: str,
    limit: int = 10,
    method: str = "hybrid",
) -> list[SearchHit]:
    """
    Search for semantically similar content in the commonplace.

    Args:
        db_path: Path to the SQLite database file
        query: The search query string
        limit: Maximum number of results to return
        method: Search method: "semantic", "fts", or "hybrid"

    Returns:
        List of search hits ordered by relevance

    Raises:
        FileNotFoundError: If the index doesn't exist
        ValueError: If the method is invalid
    """
    if not db_path.exists():
        raise FileNotFoundError("Index not found. Run 'commonplace index' first.")

    store = SQLiteVectorStore(db_path)

    # Search based on method
    if method == "fts":
        results = store.search_fts(query, limit=limit)
    elif method == "semantic":
        embedder = SentenceTransformersEmbedder()
        query_embedding = embedder.embed(query)
        results = store.search(query_embedding, limit=limit)
    elif method == "hybrid":
        embedder = SentenceTransformersEmbedder()
        query_embedding = embedder.embed(query)
        results = store.search_hybrid(query, query_embedding, limit=limit)
    else:
        store.close()
        raise ValueError(f"Unknown search method: {method}")

    store.close()
    return results
