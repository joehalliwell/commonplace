"""Vector storage implementations for similarity search."""

from collections.abc import Callable, Iterable, Iterator
from itertools import islice
from pathlib import Path
from typing import Self

import numpy as np
from numpy.typing import NDArray

from commonplace._cache import connect
from commonplace._logging import logger
from commonplace._search._types import Chunk, Embedder, IndexStat, SearchHit, SearchIndex, SearchMethod, Version
from commonplace._types import TagFilter

#: How an embedding is stored: two bytes a dimension.
_STORED = np.float16


def _to_blob(embedding: NDArray[np.float32]) -> bytes:
    return np.asarray(embedding).astype(_STORED).tobytes()


def _from_blob(blob: bytes) -> NDArray[np.float32]:
    return np.frombuffer(blob, dtype=_STORED).astype(np.float32)


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
        note_exists: Callable[[Path], bool] | None = None,
        labels: Callable[[Path], Iterable[str]] | None = None,
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
            labels: A note's labels as they stand, asked of each hit a search's tag filter
                must judge; never indexed, so tagging needs no re-index. None means no note has any.
        """
        self._note_exists = note_exists
        self._labels = labels or (lambda path: ())

        try:
            self._conn = connect(db_path)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize index at '{db_path}': {e}") from e

        if embedder is None:
            from commonplace._search._embedder import get_embedder

            embedder = get_embedder()

        self._embedder = embedder

    def _note_id(self, version: Version) -> int:
        """The `notes` row for this version of a note under this store's model, created if need be."""
        key = (self._embedder.model_id, str(version.path), version.content_id)
        # Not OR IGNORE, which would also swallow the NOT NULL that refuses an uncommitted note.
        self._conn.execute(
            "INSERT INTO notes (model_id, path, content_id) VALUES (?, ?, ?) ON CONFLICT (model_id, path, content_id) DO NOTHING",
            key,
        )
        return self._conn.execute(
            "SELECT id FROM notes WHERE model_id = ? AND path = ? AND content_id = ?", key
        ).fetchone()[0]

    def other_models(self) -> dict[str, int]:
        """How many notes are indexed under each model other than this store's."""
        rows = self._conn.execute(
            "SELECT model_id, COUNT(*) FROM notes WHERE model_id != ? GROUP BY model_id", (self._embedder.model_id,)
        )
        return dict(rows.fetchall())

    def record_indexed(self, versions: Iterable[Version]) -> None:
        """Record these versions as indexed, so one that yielded no chunks is not visited again."""
        for version in versions:
            self._note_id(version)
        self._conn.commit()

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
        known = self._embeddings_by_text({str(chunk.version.path) for chunk in chunks})
        missing = list(dict.fromkeys(chunk.text for chunk in chunks if chunk.text not in known))
        if missing:
            known.update(zip(missing, self._embedder.embed_docs(missing)))

        self._add_with_embeddings((chunk, known[chunk.text]) for chunk in chunks)

    def _embeddings_by_text(self, paths: set[str]) -> dict[str, NDArray[np.float32]]:
        """This model's stored embeddings for any version of the notes at `paths`, by chunk text."""
        rows = self._conn.execute(
            "SELECT c.text, c.embedding FROM chunks c JOIN notes n ON n.id = c.note_id"
            f" WHERE n.model_id = ? AND n.path IN ({', '.join('?' * len(paths))})",
            (self._embedder.model_id, *paths),
        )
        return {text: _from_blob(blob) for text, blob in rows}

    def _add_with_embeddings(self, chunks: Iterable[tuple[Chunk, NDArray[np.float32]]]) -> None:
        """Store each chunk with its embedding in one transaction, so a refusal leaves none of them behind."""
        with self._conn:
            for chunk, embedding in chunks:
                self._conn.execute(
                    "INSERT OR REPLACE INTO chunks (note_id, section, text, offset, embedding) VALUES (?, ?, ?, ?, ?)",
                    (self._note_id(chunk.version), chunk.section, chunk.text, chunk.offset, _to_blob(embedding)),
                )

    def search(
        self,
        query: str,
        limit: int = 10,
        method: SearchMethod = SearchMethod.HYBRID,
        include_deleted: bool = False,
        tags: TagFilter = TagFilter(),
    ) -> list[SearchHit]:
        """
        Search for matching chunks using the specified method.

        Args:
            query: The search query text
            limit: Maximum number of results to return
            method: Search method - semantic, keyword, or hybrid (default)
            include_deleted: Include hits whose note has since left the repository
            tags: Which notes' hits to keep, by their labels

        Returns:
            List of search hits, ordered by relevance
        """
        logger.debug(f"Searching for {query} ({limit} hits using {method})")

        if method == SearchMethod.SEMANTIC:
            return self.search_semantic(query, limit=limit, include_deleted=include_deleted, tags=tags)
        elif method == SearchMethod.KEYWORD:
            return self.search_keyword(query, limit=limit, include_deleted=include_deleted, tags=tags)
        elif method == SearchMethod.HYBRID:
            return self.search_hybrid(query, limit=limit, include_deleted=include_deleted, tags=tags)
        else:
            raise ValueError(f"Unknown search method: {method}")

    def _take_shown(
        self, ranked: Iterator[SearchHit], limit: int, include_deleted: bool, tags: TagFilter
    ) -> list[SearchHit]:
        """
        Take the best `limit` hits, dropping any whose note has left the repo or that `tags` doesn't admit.

        Filtering as the ranking is walked, rather than after truncating it, so
        dropped hits cost the caller nothing: a query still fills its limit with
        whatever is left.
        """
        note_exists = None if include_deleted else self._note_exists

        def shown(hit: SearchHit) -> bool:
            path = hit.chunk.version.path
            return tags.admits(self._labels(path)) and (note_exists is None or note_exists(path))

        return list(islice(filter(shown, ranked), limit))

    def search_semantic(
        self, query: str, limit: int = 10, include_deleted: bool = False, tags: TagFilter = TagFilter()
    ) -> list[SearchHit]:
        """
        Search for similar chunks using semantic similarity.

        Args:
            query: The search query text
            limit: Maximum number of results to return
            include_deleted: Include hits whose note has since left the repository
            tags: Which notes' hits to keep, by their labels

        Returns:
            List of search hits, ordered by descending similarity
        """
        query_embedding = self._embedder.embed_query(query)
        return self._search_by_embedding(query_embedding, limit, include_deleted, tags)

    def _search_by_embedding(
        self,
        query_embedding: NDArray[np.float32],
        limit: int = 10,
        include_deleted: bool = False,
        tags: TagFilter = TagFilter(),
    ) -> list[SearchHit]:
        """
        Internal method to search by embedding vector.

        Args:
            query_embedding: The query embedding vector
            limit: Maximum number of results to return
            include_deleted: Include hits whose note has since left the repository
            tags: Which notes' hits to keep, by their labels

        Returns:
            List of search hits, ordered by descending similarity
        """
        rows = self._conn.execute(
            "SELECT c.id, c.embedding FROM chunks c JOIN notes n ON n.id = c.note_id WHERE n.model_id = ?",
            (self._embedder.model_id,),
        ).fetchall()

        if not rows:
            return []

        chunk_ids = [chunk_id for chunk_id, _ in rows]
        embeddings_matrix = _from_blob(b"".join(blob for _, blob in rows)).reshape(len(rows), -1)
        similarities = self._cosine_similarity(query_embedding, embeddings_matrix)

        # Hydrate each chunk only as `_take_shown` walks the ranking, so skipped or tail rows cost nothing.
        ranked = (
            SearchHit(chunk=self._fetch_chunk(chunk_ids[idx]), score=float(similarities[idx]))
            for idx in np.argsort(similarities)[::-1]
        )
        return self._take_shown(ranked, limit, include_deleted, tags)

    def _fetch_chunk(self, chunk_id: int) -> Chunk:
        """Load one chunk by primary key, once ranking has reached it."""
        path, content_id, section, text, offset = self._conn.execute(
            "SELECT n.path, n.content_id, c.section, c.text, c.offset"
            " FROM chunks c JOIN notes n ON n.id = c.note_id WHERE c.id = ?",
            (chunk_id,),
        ).fetchone()
        return Chunk(version=Version(Path(path), content_id), section=section, text=text, offset=offset)

    @staticmethod
    def _sanitize_fts5_query(query: str) -> str:
        """Quote each word of a natural language query as an FTS5 string, so nothing in it parses as syntax."""
        return " ".join('"' + token.replace('"', '""') + '"' for token in query.split())

    def search_keyword(
        self, query: str, limit: int = 10, include_deleted: bool = False, tags: TagFilter = TagFilter()
    ) -> list[SearchHit]:
        """
        Search for chunks using keyword (full-text) search.

        Args:
            query: The search query string
            limit: Maximum number of results to return
            include_deleted: Include hits whose note has since left the repository
            tags: Which notes' hits to keep, by their labels

        Returns:
            List of search hits, ordered by BM25 rank
        """
        # No SQL LIMIT: the cursor is consumed lazily and abandoned once the
        # limit is filled, which leaves room to skip hits that are no longer live.
        cursor = self._conn.execute(
            """
            SELECT c.id, n.path, n.content_id, c.section, c.text, c.offset, rank
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.id
            JOIN notes n ON n.id = c.note_id
            WHERE chunks_fts MATCH ? AND n.model_id = ?
            ORDER BY rank
            """,
            (self._sanitize_fts5_query(query), self._embedder.model_id),
        )

        def ranked() -> Iterator[SearchHit]:
            for _chunk_id, path, content_id, section, text, offset, rank in cursor:
                version = Version(Path(path), content_id)
                chunk = Chunk(version=version, section=section, text=text, offset=offset)
                # Convert BM25 rank (negative, lower is better) to positive score
                yield SearchHit(chunk=chunk, score=-float(rank))

        return self._take_shown(ranked(), limit, include_deleted, tags)

    def search_hybrid(
        self,
        query: str,
        limit: int = 10,
        k: int = 60,
        include_deleted: bool = False,
        tags: TagFilter = TagFilter(),
    ) -> list[SearchHit]:
        """
        Search using a modified reciprocal rank fusion of keyword and semantic search.

        Each leg is oversampled to `max(limit * 3, 50)` before fusion so consensus
        hits ranked past `limit` in either leg are not dropped prematurely.

        Args:
            query: The search query string
            limit: Maximum number of results to return
            k: RRF constant (default 60, as recommended in literature)
            include_deleted: Include hits whose note has since left the repository
            tags: Which notes' hits to keep, by their labels

        Returns:
            List of search hits, ordered by fused score
        """
        if limit <= 0:
            return []

        # Oversample both legs before fusing so a consensus hit just past `limit` in either leg isn't cut prematurely.
        pool = max(limit * 3, 50)
        keyword_results = self.search_keyword(query, pool, include_deleted, tags)
        semantic_results = self.search_semantic(query, pool, include_deleted, tags)

        # Build lookup by chunk identity (path + offset uniquely identifies a chunk)
        def chunk_key(chunk: Chunk) -> tuple:
            return (str(chunk.version.path), chunk.offset)

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

    def get_indexed_paths(self) -> Iterable[Version]:
        """Each note version indexed under this store's model: its path, and git's id for the content it was read at."""
        cursor = self._conn.execute("SELECT path, content_id FROM notes WHERE model_id = ?", (self._embedder.model_id,))
        for path, content_id in cursor.fetchall():
            yield Version(Path(path), content_id)

    def remove(self, versions: Iterable[Version]) -> int:
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
        keys = [(str(version.path), version.content_id, model_id) for version in versions]

        if not keys:
            return 0

        # A note's chunks go with it, by cascade; count them first, since rowcount sees only the notes.
        removed = 0
        for key in keys:
            removed += self._conn.execute(
                "SELECT COUNT(*) FROM chunks c JOIN notes n ON n.id = c.note_id"
                " WHERE n.path = ? AND n.content_id = ? AND n.model_id = ?",
                key,
            ).fetchone()[0]
        self._conn.executemany("DELETE FROM notes WHERE path = ? AND content_id = ? AND model_id = ?", keys)
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

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

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
            "SELECT n.model_id, n.path, n.content_id, COUNT(c.id) FROM notes n LEFT JOIN chunks c ON c.note_id = n.id"
            " GROUP BY n.id"
        ):
            yield IndexStat(row[0], Version(Path(row[1]), row[2]), num_chunks=row[3])

    def chunks_for(self, path: Path) -> dict[str, int]:
        """Chunk counts indexed under this store's model for `path`, keyed by `content_id`."""
        rows = self._conn.execute(
            "SELECT n.content_id, COUNT(c.id) FROM notes n LEFT JOIN chunks c ON c.note_id = n.id"
            " WHERE n.model_id = ? AND n.path = ? GROUP BY n.id",
            (self._embedder.model_id, str(path)),
        )
        return dict(rows.fetchall())
