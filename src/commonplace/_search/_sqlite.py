"""Vector storage implementations for similarity search."""

import sqlite3
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
from numpy.typing import NDArray

from commonplace._logging import logger
from commonplace._search._types import Chunk, Embedder, IndexStat, SearchHit, SearchIndex, SearchMethod
from commonplace._types import RepoPath


class SQLiteSearchIndex(SearchIndex):
    """
    Vector store using SQLite with brute-force cosine similarity search.

    Stores chunks and their embeddings in a SQLite database, performing
    in-memory similarity search using numpy.
    """

    def __init__(self, db_path: Path, embedder: Embedder | None = None):
        """
        Initialize the vector store.

        Args:
            db_path: Path to the SQLite database file
            embedder: Embedder instance to use for generating embeddings
        """
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(db_path))
            self._create_tables()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize index at '{db_path}': {e}") from e

        if embedder is None:
            from commonplace._search._embedder import get_embedder

            embedder = get_embedder()

        self._embedder = embedder

    def _create_tables(self) -> None:
        """Create the necessary database tables if they don't exist."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL,
                path TEXT NOT NULL,
                ref TEXT NOT NULL,
                section TEXT NOT NULL,
                text TEXT NOT NULL,
                offset INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                UNIQUE(model_id, path, ref, offset)
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_path_ref ON chunks(path, ref)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_model ON chunks(model_id)")

        # Create FTS5 virtual table for full-text search
        self._conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                section,
                content=chunks,
                content_rowid=id
            )
            """
        )

        # Create triggers to keep FTS in sync
        self._conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, text, section) VALUES (new.id, new.text, new.section);
            END
            """
        )
        self._conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, text, section)
                VALUES('delete', old.id, old.text, old.section);
            END
            """
        )
        self._conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, text, section)
                VALUES('delete', old.id, old.text, old.section);
                INSERT INTO chunks_fts(rowid, text, section) VALUES (new.id, new.text, new.section);
            END
            """
        )

        self._conn.commit()

    def add_chunk(self, chunk: Chunk) -> None:
        """
        Embed and add a chunk to the store.

        Args:
            chunk: The chunk to store
        """
        embedding = self._embedder.embed(chunk.text)
        self._add_with_embedding(chunk, embedding)

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """
        Embed and add multiple chunks to the store in a batch.

        This is more efficient than calling add_chunk repeatedly,
        as it embeds all chunks in a single batch operation.

        Args:
            chunks: List of chunks to store
        """
        if not chunks:
            return

        # Batch embed all chunks
        texts = [chunk.text for chunk in chunks]
        embeddings = self._embedder.embed_batch(texts)

        # Add all chunks with their embeddings
        for chunk, embedding in zip(chunks, embeddings):
            self._add_with_embedding(chunk, embedding)

    def _add_with_embedding(self, chunk: Chunk, embedding: NDArray[np.float32]) -> None:
        """
        Internal method to add a chunk with a pre-computed embedding.

        Args:
            chunk: The chunk to store
            embedding: The chunk's embedding vector
        """
        embedding_bytes = embedding.tobytes()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO chunks (path, ref, section, text, offset, embedding, model_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(chunk.repo_path.path),
                chunk.repo_path.ref,
                chunk.section,
                chunk.text,
                chunk.offset,
                embedding_bytes,
                self._embedder.model_id,
            ),
        )
        self._conn.commit()

    def search(self, query: str, limit: int = 10, method: SearchMethod = SearchMethod.HYBRID) -> list[SearchHit]:
        """
        Search for matching chunks using the specified method.

        Args:
            query: The search query text
            limit: Maximum number of results to return
            method: Search method - semantic, keyword, or hybrid (default)

        Returns:
            List of search hits, ordered by relevance
        """
        logger.debug(f"Searching for {query} ({limit} hits using {method})")

        if method == SearchMethod.SEMANTIC:
            return self.search_semantic(query, limit=limit)
        elif method == SearchMethod.KEYWORD:
            return self.search_keyword(query, limit=limit)
        elif method == SearchMethod.HYBRID:
            return self.search_hybrid(query, limit=limit)
        else:
            raise ValueError(f"Unknown search method: {method}")

    def search_semantic(self, query: str, limit: int = 10) -> list[SearchHit]:
        """
        Search for similar chunks using semantic similarity.

        Args:
            query: The search query text
            limit: Maximum number of results to return

        Returns:
            List of search hits, ordered by descending similarity
        """
        query_embedding = self._embedder.embed(query)
        return self._search_by_embedding(query_embedding, limit)

    def _search_by_embedding(self, query_embedding: NDArray[np.float32], limit: int = 10) -> list[SearchHit]:
        """
        Internal method to search by embedding vector.

        Args:
            query_embedding: The query embedding vector
            limit: Maximum number of results to return

        Returns:
            List of search hits, ordered by descending similarity
        """
        cursor = self._conn.execute(
            "SELECT id, path, ref, section, text, offset, embedding FROM chunks WHERE model_id = ?",
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

        # Sort by similarity (descending) and take top k
        top_indices = np.argsort(similarities)[::-1][:limit]

        # Build results
        results = []
        for idx in top_indices:
            results.append(SearchHit(chunk=chunks[idx], score=float(similarities[idx])))

        return results

    def search_keyword(self, query: str, limit: int = 10) -> list[SearchHit]:
        """
        Search for chunks using keyword (full-text) search.

        Args:
            query: The search query string
            limit: Maximum number of results to return

        Returns:
            List of search hits, ordered by BM25 rank
        """
        cursor = self._conn.execute(
            """
            SELECT c.id, c.path, c.ref, c.section, c.text, c.offset, rank
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.id
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        )
        rows = cursor.fetchall()

        results = []
        for row in rows:
            chunk_id, path, ref_str, section, text, offset, rank = row
            repo_path = RepoPath(path=Path(path), ref=ref_str)
            chunk = Chunk(repo_path=repo_path, section=section, text=text, offset=offset)
            # Convert BM25 rank (negative, lower is better) to positive score
            score = -float(rank)
            results.append(SearchHit(chunk=chunk, score=score))

        return results

    def search_hybrid(
        self,
        query: str,
        limit: int = 10,
        k: int = 60,
    ) -> list[SearchHit]:
        """
        Search using a modified reciprocal rank fusion of keyword and semantic search.

        Args:
            query: The search query string
            limit: Maximum number of results to return
            k: RRF constant (default 60, as recommended in literature)

        Returns:
            List of search hits, ordered by fused score
        """

        # Get results from both methods
        keyword_results = self.search_keyword(query, limit=limit)
        semantic_results = self.search_semantic(query, limit=limit)

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
        cursor = self._conn.execute(
            "SELECT DISTINCT path, ref FROM chunks WHERE model_id = ?", (self._embedder.model_id,)
        )
        for path, ref in cursor.fetchall():
            yield (RepoPath(Path(path), ref))

    def clear(self) -> None:
        """Remove all chunks from the store."""
        self._conn.execute("DELETE FROM chunks")
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

        for row in self._conn.execute("SELECT model_id, path, ref, COUNT(*) FROM chunks GROUP BY model_id, path, ref"):
            yield IndexStat(row[0], RepoPath(Path(row[1]), row[2]), num_chunks=row[3])
