"""Semantic search components for commonplace."""

from commonplace import logger
from commonplace._repo import Commonplace
from commonplace._search._chunker import MarkdownChunker
from commonplace._search._types import (
    SearchHit as SearchHit,
)
from commonplace._search._types import (
    SearchIndex,
)
from commonplace._search._types import (
    SearchMethod as SearchMethod,
)
from commonplace._utils import batched, progress_track


def index(
    repo: Commonplace,
    store: SearchIndex,
    rebuild: bool = False,
    batch_size: int = 64,
) -> None:
    """
    Build or rebuild the search index for semantic search.

    Args:
        repo: The commonplace repository
        store: The search index to populate
        rebuild: If True, clear existing index before rebuilding
        batch_size: Number of chunks to embed in each batch (default: 64)
    """
    chunker = MarkdownChunker()

    if rebuild:
        logger.info("Clearing existing index")
        store.clear()

    # Collect notes to index
    to_index = set(repo.note_paths())
    if not rebuild:
        to_index.difference_update(store.get_indexed_paths())

    logger.info(f"Indexing {len(to_index)} notes")

    # Stream chunks from all notes and batch them for efficient embedding
    def chunk_stream():
        for path in progress_track(to_index, "Indexing notes"):
            note = repo.get_note(path)
            yield from chunker.chunk(note)

    # Process chunks in batches
    for chunk_batch in batched(chunk_stream(), batch_size):
        store.add_chunks(chunk_batch)

    logger.info("Indexing complete")
