"""Semantic search components for commonplace."""

from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace
from commonplace._search._chunker import MarkdownChunker
from commonplace._search._types import SearchHit, SearchMethod
from commonplace._utils import batched

# SearchHit/SearchMethod are imported for re-export, not used here.
__all__ = ["SearchHit", "SearchMethod", "index"]


def index(
    repo: Commonplace,
    rebuild: bool = False,
    batch_size: int = 64,
    prune: bool = True,
) -> None:
    """
    Build or rebuild the search index for semantic search.

    Args:
        repo: The commonplace repository
        store: The search index to populate
        rebuild: If True, clear existing index before rebuilding
        batch_size: Number of chunks to embed in each batch (default: 64)
        prune: If True, drop chunks for notes that have been deleted or edited
            since they were indexed (default: True)
    """
    chunker = MarkdownChunker()

    if rebuild:
        logger.info("Clearing existing index")
        repo.index.clear()

    # Every version currently in the repo. Anything else in the index is a note
    # that has since been deleted, or an older version of one that was edited.
    live = list(repo.note_paths())

    if prune:
        repo.index.prune(live)

    # Collect notes to index
    to_index = set(live)
    if not rebuild:
        to_index.difference_update(repo.index.get_indexed_paths())

    logger.info(f"Indexing {len(to_index)} notes")

    # Stream chunks from all notes and batch them for efficient embedding
    def chunk_stream():
        for path in track(to_index, "Indexing notes"):
            note = repo.get_note(path)
            yield from chunker.chunk(note)

    # Process chunks in batches
    for chunk_batch in batched(chunk_stream(), batch_size):
        repo.index.add_chunks(chunk_batch)

    logger.info("Indexing complete")
