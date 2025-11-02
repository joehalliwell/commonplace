"""Tests for vector storage."""

import numpy as np
import pytest

from commonplace._search._sqlite import SQLiteSearchIndex


def test_add_and_search(test_index, make_chunk):
    """Test adding chunks and searching for similar ones."""
    # Create some test chunks and embeddings
    chunk1 = make_chunk(
        path="test1.md",
        section="Section 1",
        text="The cat sat on the mat.",
        offset=0,
    )
    emb1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    chunk2 = make_chunk(
        path="test2.md",
        section="Section 2",
        text="A dog played in the park.",
        offset=10,
    )
    emb2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    chunk3 = make_chunk(
        path="test3.md",
        section="Section 3",
        text="The feline rested on the rug.",
        offset=20,
    )
    emb3 = np.array([0.9, 0.1, 0.0], dtype=np.float32)

    # Add chunks
    test_index._add_with_embedding(chunk1, emb1)
    test_index._add_with_embedding(chunk2, emb2)
    test_index._add_with_embedding(chunk3, emb3)

    # Search for something similar to chunk1
    query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    results = test_index._search_by_embedding(query, limit=3)

    assert len(results) == 3
    # First result should be chunk1 (exact match)
    assert results[0].chunk.text == chunk1.text
    assert results[0].score == pytest.approx(1.0, abs=1e-5)
    # Second should be chunk3 (similar embedding)
    assert results[1].chunk.text == chunk3.text
    # Third should be chunk2 (different)
    assert results[2].chunk.text == chunk2.text


def test_search_empty_store(test_index):
    """Test searching in an empty store."""
    query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    results = test_index._search_by_embedding(query, limit=10)
    assert len(results) == 0


def test_clear(test_index, make_chunk):
    """Test clearing the store."""
    chunk = make_chunk(
        path="test.md",
        section="Section",
        text="Some text",
        offset=0,
    )
    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    test_index._add_with_embedding(chunk, emb)

    # Verify it was added
    query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    results = test_index._search_by_embedding(query, limit=10)
    assert len(results) == 1

    # Clear and verify it's empty
    test_index.clear()
    results = test_index._search_by_embedding(query, limit=10)
    assert len(results) == 0


def test_limit_results(test_index, make_chunk):
    """Test that limit parameter works."""
    # Add 5 chunks
    for i in range(5):
        chunk = make_chunk(
            path=f"test{i}.md",
            section=f"Section {i}",
            text=f"Text {i}",
            offset=i * 10,
        )
        emb = np.random.rand(3).astype(np.float32)
        test_index._add_with_embedding(chunk, emb)

    # Search with limit=3
    query = np.random.rand(3).astype(np.float32)
    results = test_index._search_by_embedding(query, limit=3)
    assert len(results) == 3


def test_cosine_similarity():
    """Test the cosine similarity calculation."""
    query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    embeddings = np.array(
        [
            [1.0, 0.0, 0.0],  # Same direction (similarity = 1.0)
            [0.0, 1.0, 0.0],  # Orthogonal (similarity = 0.0)
            [-1.0, 0.0, 0.0],  # Opposite (similarity = -1.0)
            [0.5, 0.5, 0.0],  # 45 degrees (similarity ≈ 0.707)
        ],
        dtype=np.float32,
    )

    similarities = SQLiteSearchIndex._cosine_similarity(query, embeddings)

    assert similarities[0] == pytest.approx(1.0, abs=1e-5)
    assert similarities[1] == pytest.approx(0.0, abs=1e-5)
    assert similarities[2] == pytest.approx(-1.0, abs=1e-5)
    assert similarities[3] == pytest.approx(0.707, abs=1e-2)


def test_get_indexed_paths(test_index, make_chunk):
    """Test retrieving indexed paths."""
    # Empty store should return empty set
    paths = set(test_index.get_indexed_paths())
    assert len(paths) == 0

    # Add chunks from different paths
    chunk1 = make_chunk(path="note1.md", section="Section", text="Text 1", offset=0)
    chunk2 = make_chunk(path="note1.md", section="Section", text="Text 2", offset=10)
    chunk3 = make_chunk(path="note2.md", section="Section", text="Text 3", offset=0)

    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    test_index._add_with_embedding(chunk1, emb)
    test_index._add_with_embedding(chunk2, emb)
    test_index._add_with_embedding(chunk3, emb)

    # Should return unique paths
    paths = set(test_index.get_indexed_paths())
    assert len(paths) == 2
    assert chunk1.repo_path in paths
    assert chunk2.repo_path in paths


def test_stats_empty(test_index):
    stats = list(test_index.stats())
    assert len(stats) == 0


def test_add_chunks_batch(test_index, make_chunk):
    """Test adding multiple chunks in a batch."""
    # Create test chunks
    chunks = [make_chunk(path="test1.md", section="Section 1", text=f"Text {i}", offset=i * 10) for i in range(5)]

    # Add chunks in batch
    test_index.add_chunks(chunks)

    # Verify all chunks were added by searching
    paths = list(test_index.get_indexed_paths())
    assert len(paths) == 1
    assert paths[0].path.name == "test1.md"

    # Verify we can search and find them
    results = test_index.search("test query", limit=10)
    assert len(results) == 5


def test_add_chunks_empty_batch(test_index):
    """Test adding an empty batch (should be a no-op)."""
    # Should not raise an error
    test_index.add_chunks([])

    # Store should still be empty
    paths = list(test_index.get_indexed_paths())
    assert len(paths) == 0
