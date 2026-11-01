"""Vector storage implementations for similarity search."""

import sqlite3
from collections.abc import Callable, Iterable, Iterator
from itertools import islice
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from commonplace._logging import logger
from commonplace._search._types import Chunk, Embedder, IndexStat, SearchHit, SearchIndex, SearchMethod
from commonplace._types import RepoPath

#: The schema this store writes, stamped as `user_version`. Version 1 predates the stamp: a database
#: whose every chunk named its own model, path and ref. Version 2 names a note once, in `notes`, which
#: also records a note that yields no chunks, so it is visited once rather than on every run.
INDEX_VERSION = 2

_NOTES_DDL = """
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    model_id TEXT NOT NULL,
    path TEXT NOT NULL,
    ref TEXT NOT NULL,
    UNIQUE(model_id, path, ref)
);
"""

_CHUNKS_DDL = """
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    section TEXT NOT NULL,
    text TEXT NOT NULL,
    offset INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    UNIQUE(note_id, offset)
);
"""

#: What keeps full-text search in step with `chunks`.
_TRIGGERS_DDL = """
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, section) VALUES (new.id, new.text, new.section);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section) VALUES('delete', old.id, old.text, old.section);
END;
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section) VALUES('delete', old.id, old.text, old.section);
    INSERT INTO chunks_fts(rowid, text, section) VALUES (new.id, new.text, new.section);
END;
"""

_FRESH = f"""
BEGIN;
{_NOTES_DDL}
{_CHUNKS_DDL}
CREATE VIRTUAL TABLE chunks_fts USING fts5(text, section, content=chunks, content_rowid=id);
{_TRIGGERS_DDL}
PRAGMA user_version = {INDEX_VERSION};
COMMIT;
"""

# Chunk ids are kept, so the external-content full-text index still points at the right rows, and no
# embedding is recomputed. The copy runs before the new triggers exist, or it would re-add every row to
# the full-text index; dropping v1's table takes its own indexes and triggers with it.
_MIGRATE_V1 = f"""
BEGIN;
{_NOTES_DDL}
INSERT INTO notes (model_id, path, ref)
    SELECT model_id, path, ref FROM chunks GROUP BY model_id, path, ref ORDER BY MIN(id);
ALTER TABLE chunks RENAME TO chunks_v1;
{_CHUNKS_DDL}
INSERT INTO chunks (id, note_id, section, text, offset, embedding)
    SELECT c.id, n.id, c.section, c.text, c.offset, c.embedding
    FROM chunks_v1 c JOIN notes n ON (n.model_id, n.path, n.ref) = (c.model_id, c.path, c.ref);
DROP TABLE chunks_v1;
{_TRIGGERS_DDL}
PRAGMA user_version = {INDEX_VERSION};
COMMIT;
"""


class SQLiteSearchIndex(SearchIndex):
    """
    Vector store using SQLite with brute-force cosine similarity search.

    Stores chunks and their embeddings in a SQLite database, performing
    in-memory similarity search using numpy.
    """

    def __init__(
        self,
        db_path: Path,
        embedder: Embedder | None = None,
        note_exists: Callable[[RepoPath], bool] | None = None,
    ):
        """
        Initialize the vector store.

        Args:
            db_path: Path to the SQLite database file
            embedder: Embedder instance to use for generating embeddings
            note_exists: Whether an indexed chunk's note is still in the
                repository. Hits that fail it are hidden from results unless the
                caller asks for deleted ones. None (the default) means this store
                has no repository to ask, and every hit stands.
        """
        self._note_exists = note_exists

        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(db_path))
            self._open_schema()
            # Per connection, and off by default: without it, removing a note would orphan its chunks.
            self._conn.execute("PRAGMA foreign_keys = ON")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize index at '{db_path}': {e}") from e

        if embedder is None:
            from commonplace._search._embedder import get_embedder

            embedder = get_embedder()

        self._embedder = embedder

    def _open_schema(self) -> None:
        """Create a fresh index, migrate an older one in place, or refuse one newer than this release."""
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version == INDEX_VERSION:
            return
        if version > INDEX_VERSION:
            raise RuntimeError(
                f"schema v{version} is newer than this release's v{INDEX_VERSION}: upgrade, or delete it"
            )
        if not self._conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunks'").fetchone():
            self._conn.executescript(_FRESH)
            return
        logger.info(f"Migrating the search index to schema v{INDEX_VERSION}")
        self._conn.executescript(_MIGRATE_V1)
        # The migration frees v1's per-chunk identity columns; only a vacuum gives the space back.
        self._conn.execute("VACUUM")

    def _note_id(self, repo_path: RepoPath) -> int:
        """The `notes` row for this version of a note under this store's model, created if need be."""
        key = (self._embedder.model_id, str(repo_path.path), repo_path.ref)
        # Not OR IGNORE, which would also swallow the NOT NULL that refuses an uncommitted note.
        self._conn.execute(
            "INSERT INTO notes (model_id, path, ref) VALUES (?, ?, ?) ON CONFLICT (model_id, path, ref) DO NOTHING", key
        )
        return self._conn.execute("SELECT id FROM notes WHERE model_id = ? AND path = ? AND ref = ?", key).fetchone()[0]

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """
        Embed and add multiple chunks to the store in a batch.

        Args:
            chunks: List of chunks to store
        """
        if not chunks:
            return

        # A chunk whose text another version of its note already has keeps that embedding: an edit
        # makes the whole note new to the index, but usually changes few of its chunks.
        known = self._embeddings_by_text({str(chunk.repo_path.path) for chunk in chunks})
        missing = list(dict.fromkeys(chunk.text for chunk in chunks if chunk.text not in known))
        if missing:
            known.update(zip(missing, self._embedder.embed_docs(missing)))

        for chunk in chunks:
            self._add_with_embedding(chunk, known[chunk.text])

    def _embeddings_by_text(self, paths: set[str]) -> dict[str, NDArray[np.float32]]:
        """This model's stored embeddings for any version of the notes at `paths`, by chunk text."""
        rows = self._conn.execute(
            "SELECT c.text, c.embedding FROM chunks c JOIN notes n ON n.id = c.note_id"
            f" WHERE n.model_id = ? AND n.path IN ({', '.join('?' * len(paths))})",
            (self._embedder.model_id, *paths),
        )
        return {text: np.frombuffer(blob, dtype=np.float32) for text, blob in rows}

    def _add_with_embedding(self, chunk: Chunk, embedding: NDArray[np.float32]) -> None:
        """
        Internal method to add a chunk with a pre-computed embedding.

        Args:
            chunk: The chunk to store
            embedding: The chunk's embedding vector
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO chunks (note_id, section, text, offset, embedding) VALUES (?, ?, ?, ?, ?)",
            (self._note_id(chunk.repo_path), chunk.section, chunk.text, chunk.offset, embedding.tobytes()),
        )
        self._conn.commit()

    def search(
        self,
        query: str,
        limit: int = 10,
        method: SearchMethod = SearchMethod.HYBRID,
        include_deleted: bool = False,
    ) -> list[SearchHit]:
        """
        Search for matching chunks using the specified method.

        Args:
            query: The search query text
            limit: Maximum number of results to return
            method: Search method - semantic, keyword, or hybrid (default)
            include_deleted: Include hits whose note has since left the repository

        Returns:
            List of search hits, ordered by relevance
        """
        logger.debug(f"Searching for {query} ({limit} hits using {method})")

        if method == SearchMethod.SEMANTIC:
            return self.search_semantic(query, limit=limit, include_deleted=include_deleted)
        elif method == SearchMethod.KEYWORD:
            return self.search_keyword(query, limit=limit, include_deleted=include_deleted)
        elif method == SearchMethod.HYBRID:
            return self.search_hybrid(query, limit=limit, include_deleted=include_deleted)
        else:
            raise ValueError(f"Unknown search method: {method}")

    def _take_undeleted(self, ranked: Iterator[SearchHit], limit: int, include_deleted: bool) -> list[SearchHit]:
        """
        Take the best `limit` hits, dropping any whose note has left the repo.

        Filtering as the ranking is walked, rather than after truncating it, so
        hidden hits cost the caller nothing: a query still fills its limit with
        whatever is left.
        """
        if include_deleted or self._note_exists is None:
            return list(islice(ranked, limit))
        note_exists = self._note_exists
        return list(islice((hit for hit in ranked if note_exists(hit.chunk.repo_path)), limit))

    def search_semantic(self, query: str, limit: int = 10, include_deleted: bool = False) -> list[SearchHit]:
        """
        Search for similar chunks using semantic similarity.

        Args:
            query: The search query text
            limit: Maximum number of results to return
            include_deleted: Include hits whose note has since left the repository

        Returns:
            List of search hits, ordered by descending similarity
        """
        query_embedding = self._embedder.embed_query(query)
        return self._search_by_embedding(query_embedding, limit, include_deleted=include_deleted)

    def _search_by_embedding(
        self, query_embedding: NDArray[np.float32], limit: int = 10, include_deleted: bool = False
    ) -> list[SearchHit]:
        """
        Internal method to search by embedding vector.

        Args:
            query_embedding: The query embedding vector
            limit: Maximum number of results to return
            include_deleted: Include hits whose note has since left the repository

        Returns:
            List of search hits, ordered by descending similarity
        """
        cursor = self._conn.execute(
            "SELECT c.id, n.path, n.ref, c.section, c.text, c.offset, c.embedding"
            " FROM chunks c JOIN notes n ON n.id = c.note_id WHERE n.model_id = ?",
            (self._embedder.model_id,),
        )
        rows = cursor.fetchall()

        if not rows:
            return []

        # Load all embeddings
        embeddings = []
        chunks = []
        chunk_ids = []
        for row in rows:
            chunk_id, path, ref_str, section, text, offset, embedding_bytes = row
            embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
            embeddings.append(embedding)

            repo_path = RepoPath(path=Path(path), ref=ref_str)
            chunks.append(Chunk(repo_path=repo_path, section=section, text=text, offset=offset))
            chunk_ids.append(chunk_id)

        # Compute cosine similarities
        embeddings_matrix = np.array(embeddings)
        similarities = self._cosine_similarity(query_embedding, embeddings_matrix)

        # Sort by similarity (descending), then walk the ranking until the limit is filled
        ranked = (
            SearchHit(chunk=chunks[idx], score=float(similarities[idx])) for idx in np.argsort(similarities)[::-1]
        )
        return self._take_undeleted(ranked, limit, include_deleted)

    @staticmethod
    def _sanitize_fts5_query(query: str) -> str:
        """Quote each word of a natural language query as an FTS5 string, so nothing in it parses as syntax."""
        return " ".join('"' + token.replace('"', '""') + '"' for token in query.split())

    def search_keyword(self, query: str, limit: int = 10, include_deleted: bool = False) -> list[SearchHit]:
        """
        Search for chunks using keyword (full-text) search.

        Args:
            query: The search query string
            limit: Maximum number of results to return
            include_deleted: Include hits whose note has since left the repository

        Returns:
            List of search hits, ordered by BM25 rank
        """
        # No SQL LIMIT: the cursor is consumed lazily and abandoned once the
        # limit is filled, which leaves room to skip hits that are no longer live.
        cursor = self._conn.execute(
            """
            SELECT c.id, n.path, n.ref, c.section, c.text, c.offset, rank
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.id
            JOIN notes n ON n.id = c.note_id
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            """,
            (self._sanitize_fts5_query(query),),
        )

        def ranked() -> Iterator[SearchHit]:
            for _chunk_id, path, ref_str, section, text, offset, rank in cursor:
                repo_path = RepoPath(path=Path(path), ref=ref_str)
                chunk = Chunk(repo_path=repo_path, section=section, text=text, offset=offset)
                # Convert BM25 rank (negative, lower is better) to positive score
                yield SearchHit(chunk=chunk, score=-float(rank))

        return self._take_undeleted(ranked(), limit, include_deleted)

    def search_hybrid(
        self,
        query: str,
        limit: int = 10,
        k: int = 60,
        include_deleted: bool = False,
    ) -> list[SearchHit]:
        """
        Search using a modified reciprocal rank fusion of keyword and semantic search.

        Args:
            query: The search query string
            limit: Maximum number of results to return
            k: RRF constant (default 60, as recommended in literature)
            include_deleted: Include hits whose note has since left the repository

        Returns:
            List of search hits, ordered by fused score
        """

        # Get results from both methods, each already filtered, so fusion sees
        # the same ranks a caller of either method would.
        keyword_results = self.search_keyword(query, limit=limit, include_deleted=include_deleted)
        semantic_results = self.search_semantic(query, limit=limit, include_deleted=include_deleted)

        # Build lookup by chunk identity (path + offset uniquely identifies a chunk)
        def chunk_key(chunk: Chunk) -> tuple:
            return (str(chunk.repo_path.path), chunk.offset)

        # Compute RRF scores
        rrf_scores: dict[tuple, float] = {}
        chunk_lookup: dict[tuple, Chunk] = {}

        for result_set in (keyword_results, semantic_results):
            for rank, hit in enumerate(result_set, 1):
                key = chunk_key(hit.chunk)
                rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
                chunk_lookup[key] = hit.chunk

        # Sort by RRF score and build results
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

        results = []
        for key in sorted_keys[:limit]:
            results.append(SearchHit(chunk=chunk_lookup[key], score=rrf_scores[key]))

        return results

    def get_indexed_paths(self) -> Iterable[RepoPath]:
        """
        Get mapping of paths to their indexed refs for this store's model.

        Returns:
            Dict mapping path -> set of refs
        """
        cursor = self._conn.execute("SELECT path, ref FROM notes WHERE model_id = ?", (self._embedder.model_id,))
        for path, ref in cursor.fetchall():
            yield (RepoPath(Path(path), ref))

    def remove(self, versions: Iterable[RepoPath]) -> int:
        """
        Remove this store's chunks for the given versions of notes.

        Confined to this store's model, like every other operation here: the
        store is bound to an embedder, and chunks written by another one are not
        its to delete.

        Args:
            versions: Paths/refs whose chunks should go

        Returns:
            Number of chunks removed
        """
        model_id = self._embedder.model_id
        keys = [(str(repo_path.path), repo_path.ref, model_id) for repo_path in versions]

        if not keys:
            return 0

        # A note's chunks go with it, by cascade; count them first, since rowcount sees only the notes.
        removed = 0
        for key in keys:
            removed += self._conn.execute(
                "SELECT COUNT(*) FROM chunks c JOIN notes n ON n.id = c.note_id"
                " WHERE n.path = ? AND n.ref = ? AND n.model_id = ?",
                key,
            ).fetchone()[0]
        self._conn.executemany("DELETE FROM notes WHERE path = ? AND ref = ? AND model_id = ?", keys)
        self._conn.commit()

        logger.info(f"Removed {removed} chunks from {len(keys)} deleted or superseded notes")
        return removed

    def clear(self) -> None:
        """Remove every note, and so every chunk, from the store."""
        self._conn.execute("DELETE FROM notes")
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    @staticmethod
    def _cosine_similarity(query: NDArray[np.float32], embeddings: NDArray[np.float32]) -> NDArray[np.float32]:
        """
        Compute cosine similarity between a query and multiple embeddings.

        Args:
            query: Query embedding vector, shape (embedding_dim,)
            embeddings: Matrix of embeddings, shape (n_embeddings, embedding_dim)

        Returns:
            Array of similarity scores, shape (n_embeddings,)
        """
        # Normalize query
        query_norm = query / np.linalg.norm(query)

        # Normalize embeddings
        embeddings_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        # Compute dot product (cosine similarity for normalized vectors)
        similarities = np.dot(embeddings_norm, query_norm)

        return similarities

    def stats(self) -> Iterator[IndexStat]:
        """Get statistics about the vector store."""

        for row in self._conn.execute(
            "SELECT n.model_id, n.path, n.ref, COUNT(c.id) FROM notes n LEFT JOIN chunks c ON c.note_id = n.id"
            " GROUP BY n.id"
        ):
            yield IndexStat(row[0], RepoPath(Path(row[1]), row[2]), num_chunks=row[3])
