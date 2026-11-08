"""Semantic search components for commonplace."""

from commonplace._config import CACHE
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace
from commonplace._search._chunker import MarkdownChunker
from commonplace._search._sqlite import SQLiteSearchIndex
from commonplace._search._types import SearchHit, SearchMethod, Version
from commonplace._utils import batched

# SearchHit/SearchMethod are imported for re-export, not used here.
__all__ = ["SearchHit", "SearchMethod", "index", "open_index"]


def open_index(repo: Commonplace) -> SQLiteSearchIndex:
    """The repository's search index, a cache of what it has committed, under `.commonplace/cache/`."""
    return SQLiteSearchIndex(
        repo.root / CACHE / "index.db",
        # Blind to which version: an edited note is still there to open, so a chunk of its previous text is
        # worth returning until indexing catches up. A deleted one is not, and quoting it back would be a lie.
        note_exists=lambda path: (repo.root / path).exists(),
        is_hidden=lambda path: repo.load(path).hidden,
    )


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
    chunker, store = MarkdownChunker(), open_index(repo)

    if rebuild:
        logger.info("Clearing existing index")
        store.clear()

    # What the repo holds now, against what the index already has. The two
    # differences say what to add, and what has been deleted or edited since.
    # A rebuild needs no special case: clear() just emptied `indexed`.
    ids = repo.content_ids()
    live = {Version(path, ids[path]) for path in repo.note_paths() if path in ids}
    indexed = set(store.get_indexed_paths())

    # The index holds committed versions only, but `load` reads the file on disk, so a note with
    # uncommitted changes waits for them to be committed. Its committed version, already indexed, stays live.
    uncommitted = repo.uncommitted(".")
    to_index = {version for version in live - indexed if version.path.as_posix() not in uncommitted}

    logger.info(f"Indexing {len(to_index)} notes")

    # Stream chunks from all notes and batch them for efficient embedding
    def chunk_stream():
        for version in track(to_index, "Indexing notes"):
            yield from chunker.chunk(repo.load(version.path), version.oid)

    # Process chunks in batches
    for chunk_batch in batched(chunk_stream(), batch_size):
        store.add_chunks(chunk_batch)
    # Notes with chunks are recorded already; this catches those with none.
    store.record_indexed(to_index)

    # After adding, so the versions being replaced can lend their unchanged chunks' embeddings.
    if prune:
        store.remove(indexed - live)

    # Dropping them would cost a full re-embed to undo, so this only says they're there.
    for model_id, count in store.other_models().items():
        logger.warning(
            f"{count} notes are indexed under {model_id}, which search no longer uses;"
            " `commonplace index --rebuild` drops them and reclaims the space"
        )

    logger.info("Indexing complete")
