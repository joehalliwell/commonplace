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


def test_remove_leaves_another_models_chunks_alone(test_index, other_model_index, make_chunk):
    """A store is bound to an embedder, so it removes its own chunks and no one else's.

    Both stores hold the same version of the same note, and removing it through
    one has to leave the other's copy intact.
    """
    chunk = make_chunk(path="doomed.md", section="Section", text="Long gone", offset=0)
    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    test_index._add_with_embedding(chunk, emb)
    other_model_index._add_with_embedding(chunk, emb)

    assert test_index.remove([chunk.repo_path]) == 1

    assert set(test_index.get_indexed_paths()) == set()
    assert set(other_model_index.get_indexed_paths()) == {chunk.repo_path}


def test_remove_drops_chunks_for_the_given_versions(test_index, make_chunk):
    """Removal is by (path, ref), so one version of a note can go while another stays."""
    live = make_chunk(path="live.md", section="Section", text="Still here", offset=0)
    deleted = make_chunk(path="deleted.md", section="Section", text="Long gone", offset=0)
    superseded = make_chunk(path="live.md", section="Section", text="Earlier draft", offset=0, ref="1" * 40)

    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    for chunk in (live, deleted, superseded):
        test_index._add_with_embedding(chunk, emb)

    removed = test_index.remove([deleted.repo_path, superseded.repo_path])

    assert removed == 2
    assert set(test_index.get_indexed_paths()) == {live.repo_path}


def test_remove_keeps_the_full_text_index_in_step(test_index, make_chunk):
    """A removed chunk has to leave FTS too, or keyword search resurrects it."""
    chunk = make_chunk(path="deleted.md", section="Section", text="Ozymandias king of kings", offset=0)
    test_index._add_with_embedding(chunk, np.array([1.0, 0.0, 0.0], dtype=np.float32))
    assert test_index.search_keyword("Ozymandias", limit=10)

    test_index.remove([chunk.repo_path])

    assert test_index.search_keyword("Ozymandias", limit=10) == []


def test_remove_nothing_leaves_the_index_alone(test_index, make_chunk):
    """An empty removal set removes nothing — the failure mode of getting this backwards."""
    chunk = make_chunk(path="live.md", section="Section", text="Still here", offset=0)
    test_index._add_with_embedding(chunk, np.array([1.0, 0.0, 0.0], dtype=np.float32))

    assert test_index.remove([]) == 0
    assert set(test_index.get_indexed_paths()) == {chunk.repo_path}


def test_remove_unknown_version_is_a_no_op(test_index, make_chunk):
    """Naming a version the index never held is harmless."""
    chunk = make_chunk(path="live.md", section="Section", text="Still here", offset=0)
    test_index._add_with_embedding(chunk, np.array([1.0, 0.0, 0.0], dtype=np.float32))

    stranger = make_chunk(path="live.md", section="Section", text="Never indexed", offset=0, ref="1" * 40)

    assert test_index.remove([stranger.repo_path]) == 0
    assert set(test_index.get_indexed_paths()) == {chunk.repo_path}


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
