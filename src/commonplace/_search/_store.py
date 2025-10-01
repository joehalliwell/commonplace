"""Vector storage implementations for similarity search."""

import sqlite3
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from commonplace._search._types import Chunk, SearchHit


class SQLiteVectorStore:
    """
    Vector store using SQLite with brute-force cosine similarity search.

    Stores chunks and their embeddings in a SQLite database, performing
    in-memory similarity search using numpy.
    """

    def __init__(self, db_path: Path):
        """
        Initialize the vector store.

        Args:
            db_path: Path to the SQLite database file
        """
        self._conn = sqlite3.connect(str(db_path))
        self._create_tables()

    def _create_tables(self) -> None:
        """Create the necessary database tables if they don't exist."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                section TEXT NOT NULL,
                text TEXT NOT NULL,
                offset INTEGER NOT NULL,
                embedding BLOB NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_path ON chunks(path)")

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
                INSERT INTO chunks_fts(chunks_fts, rowid, text, section) VALUES('delete', old.id, old.text, old.section);
            END
            """
        )
        self._conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, text, section) VALUES('delete', old.id, old.text, old.section);
                INSERT INTO chunks_fts(rowid, text, section) VALUES (new.id, new.text, new.section);
            END
            """
        )

        self._conn.commit()

    def add(self, chunk: Chunk, embedding: NDArray[np.float32]) -> None:
        """
        Add a chunk and its embedding to the store.

        Args:
            chunk: The chunk to store
            embedding: The chunk's embedding vector
        """
        embedding_bytes = embedding.tobytes()
        self._conn.execute(
            """
            INSERT INTO chunks (path, section, text, offset, embedding)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(chunk.path), chunk.section, chunk.text, chunk.offset, embedding_bytes),
        )
        self._conn.commit()

    def search(self, query_embedding: NDArray[np.float32], limit: int = 10) -> list[SearchHit]:
        """
        Search for similar chunks using cosine similarity.

        Args:
            query_embedding: The query embedding vector
            limit: Maximum number of results to return

        Returns:
            List of search hits, ordered by descending similarity
        """
        cursor = self._conn.execute("SELECT id, path, section, text, offset, embedding FROM chunks")
        rows = cursor.fetchall()

        if not rows:
            return []

        # Load all embeddings
        embeddings = []
        chunks = []
        chunk_ids = []
        for row in rows:
            chunk_id, path, section, text, offset, embedding_bytes = row
            embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
            embeddings.append(embedding)
            chunks.append(Chunk(path=Path(path), section=section, text=text, offset=offset))
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

    def search_fts(self, query: str, limit: int = 10) -> list[SearchHit]:
        """
        Search for chunks using full-text search.

        Args:
            query: The search query string
            limit: Maximum number of results to return

        Returns:
            List of search hits, ordered by BM25 rank
        """
        cursor = self._conn.execute(
            """
            SELECT c.id, c.path, c.section, c.text, c.offset, rank
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
            chunk_id, path, section, text, offset, rank = row
            chunk = Chunk(path=Path(path), section=section, text=text, offset=offset)
            # Convert BM25 rank (negative, lower is better) to positive score
            score = -float(rank)
            results.append(SearchHit(chunk=chunk, score=score))

        return results

    def search_hybrid(
        self, query: str, query_embedding: NDArray[np.float32], limit: int = 10, k: int = 60
    ) -> list[SearchHit]:
        """
        Search using reciprocal rank fusion of FTS and semantic search.

        Args:
            query: The search query string for FTS
            query_embedding: The query embedding vector for semantic search
            limit: Maximum number of results to return
            k: RRF constant (default 60, as recommended in literature)

        Returns:
            List of search hits, ordered by fused score
        """
        # Get results from both methods
        fts_results = self.search_fts(query, limit=limit * 2)
        semantic_results = self.search(query_embedding, limit=limit * 2)

        # Build lookup by chunk identity (path + offset uniquely identifies a chunk)
        def chunk_key(chunk: Chunk) -> tuple:
            return (str(chunk.path), chunk.offset)

        # Compute RRF scores
        rrf_scores: dict[tuple, float] = {}
        chunk_lookup: dict[tuple, Chunk] = {}

        # Add FTS results
        for rank, hit in enumerate(fts_results, 1):
            key = chunk_key(hit.chunk)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            chunk_lookup[key] = hit.chunk

        # Add semantic results
        for rank, hit in enumerate(semantic_results, 1):
            key = chunk_key(hit.chunk)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            chunk_lookup[key] = hit.chunk

        # Sort by RRF score and build results
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)[:limit]

        results = []
        for key in sorted_keys:
            results.append(SearchHit(chunk=chunk_lookup[key], score=rrf_scores[key]))

        return results

    def get_indexed_paths(self) -> set[str]:
        """
        Get all unique paths that have been indexed.

        Returns:
            Set of path strings that are present in the index
        """
        cursor = self._conn.execute("SELECT DISTINCT path FROM chunks")
        rows = cursor.fetchall()
        return {row[0] for row in rows}

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
