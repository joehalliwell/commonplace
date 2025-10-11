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
from commonplace._utils import progress_track


def index(
    repo: Commonplace,
    store: SearchIndex,
    rebuild: bool = False,
) -> None:
    """
    Build or rebuild the search index for semantic search.
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

    for path in progress_track(to_index, "Indexing notes"):
        note = repo.get_note(path)
        for chunk in chunker.chunk(note):
            store.add_chunk(chunk)

    logger.info("Indexing complete")
