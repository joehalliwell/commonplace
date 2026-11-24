"""Tests for vector storage."""

import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np
import pytest

from commonplace._search._sqlite import SQLiteSearchIndex
from commonplace._search._types import Version
from tests.conftest import FixedEmbedder


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
    test_index._add_with_embeddings([(chunk1, emb1), (chunk2, emb2), (chunk3, emb3)])

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

    test_index._add_with_embeddings([(chunk, emb)])

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
        test_index._add_with_embeddings([(chunk, emb)])

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
    test_index._add_with_embeddings([(chunk1, emb), (chunk2, emb), (chunk3, emb)])

    # Should return unique paths
    paths = set(test_index.get_indexed_paths())
    assert len(paths) == 2
    assert chunk1.version in paths
    assert chunk2.version in paths


def test_remove_leaves_another_models_chunks_alone(test_index, other_model_index, make_chunk):
    """A store is bound to an embedder, so it removes its own chunks and no one else's.

    Both stores hold the same version of the same note, and removing it through
    one has to leave the other's copy intact.
    """
    chunk = make_chunk(path="doomed.md", section="Section", text="Long gone", offset=0)
    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    test_index._add_with_embeddings([(chunk, emb)])
    other_model_index._add_with_embeddings([(chunk, emb)])

    assert test_index.remove([chunk.version]) == 1

    assert set(test_index.get_indexed_paths()) == set()
    assert set(other_model_index.get_indexed_paths()) == {chunk.version}


def test_remove_drops_chunks_for_the_given_versions(test_index, make_chunk):
    """Removal is by (path, ref), so one version of a note can go while another stays."""
    live = make_chunk(path="live.md", section="Section", text="Still here", offset=0)
    deleted = make_chunk(path="deleted.md", section="Section", text="Long gone", offset=0)
    superseded = make_chunk(path="live.md", section="Section", text="Earlier draft", offset=0, content_id="1" * 40)

    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    for chunk in (live, deleted, superseded):
        test_index._add_with_embeddings([(chunk, emb)])

    removed = test_index.remove([deleted.version, superseded.version])

    assert removed == 2
    assert set(test_index.get_indexed_paths()) == {live.version}


def test_remove_keeps_the_full_text_index_in_step(test_index, make_chunk):
    """A removed chunk has to leave FTS too, or keyword search resurrects it."""
    chunk = make_chunk(path="deleted.md", section="Section", text="Ozymandias king of kings", offset=0)
    test_index._add_with_embeddings([(chunk, np.array([1.0, 0.0, 0.0], dtype=np.float32))])
    assert test_index.search_keyword("Ozymandias", limit=10)

    test_index.remove([chunk.version])

    assert test_index.search_keyword("Ozymandias", limit=10) == []


@pytest.mark.parametrize(
    "query",
    ["I'll write", "foo: bar.baz", "see src/notes", 'say "hi"', "write -", "NEAR", "write OR"],
)
def test_search_keyword_fts5_syntax_in_query_matches_literally(test_index, make_chunk, query):
    """Punctuation and FTS5 keywords in a query are words to match, not syntax to parse."""
    text = 'I\'ll write foo: bar.baz, then see src/notes and say "hi" near or far'
    chunk = make_chunk(path="note.md", section="Section", text=text, offset=0)
    test_index._add_with_embeddings([(chunk, np.array([1.0, 0.0, 0.0], dtype=np.float32))])

    hits = test_index.search_keyword(query, limit=10)

    assert [hit.chunk for hit in hits] == [chunk]


def test_remove_nothing_leaves_the_index_alone(test_index, make_chunk):
    """An empty removal set removes nothing — the failure mode of getting this backwards."""
    chunk = make_chunk(path="live.md", section="Section", text="Still here", offset=0)
    test_index._add_with_embeddings([(chunk, np.array([1.0, 0.0, 0.0], dtype=np.float32))])

    assert test_index.remove([]) == 0
    assert set(test_index.get_indexed_paths()) == {chunk.version}


def test_remove_unknown_version_is_a_no_op(test_index, make_chunk):
    """Naming a version the index never held is harmless."""
    chunk = make_chunk(path="live.md", section="Section", text="Still here", offset=0)
    test_index._add_with_embeddings([(chunk, np.array([1.0, 0.0, 0.0], dtype=np.float32))])

    stranger = make_chunk(path="live.md", section="Section", text="Never indexed", offset=0, content_id="1" * 40)

    assert test_index.remove([stranger.version]) == 0
    assert set(test_index.get_indexed_paths()) == {chunk.version}


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


def test_add_chunk_of_uncommitted_note_is_refused(test_index, make_chunk):
    """The index holds versions only, so a chunk must name one."""
    chunk = make_chunk(path="draft.md", section="S", text="Draft text", offset=0, content_id=None)

    with pytest.raises(sqlite3.IntegrityError):
        test_index.add_chunks([chunk])

    assert list(test_index.get_indexed_paths()) == []


def test_add_chunks_refused_midway_leaves_none_of_the_batch(test_index, make_chunk):
    good = make_chunk(path="kept.md", section="S", text="Kept text", offset=0)
    bad = make_chunk(path="draft.md", section="S", text="Draft text", offset=0, content_id=None)

    with pytest.raises(sqlite3.IntegrityError):
        test_index.add_chunks([good, bad])

    assert list(test_index.get_indexed_paths()) == []


def test_search_keyword_ignores_another_models_chunks(test_index, other_model_index, make_chunk):
    """Keyword search is scoped to this store's model, just like semantic search (#318)."""
    chunk = make_chunk(path="note.md", section="S", text="Ozymandias king of kings", offset=0)
    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    other_model_index._add_with_embeddings([(chunk, emb)])

    assert test_index.search_keyword("Ozymandias", limit=10) == []

    test_index._add_with_embeddings([(chunk, emb)])
    assert [hit.chunk for hit in test_index.search_keyword("Ozymandias", limit=10)] == [chunk]


def test_search_hybrid_surfaces_consensus_past_limit(tmp_path, make_chunk):
    """Oversampling each leg before RRF lets a hit ranked #3 in both legs beat #1-in-one-leg hits (#321)."""
    with closing(SQLiteSearchIndex(tmp_path / "index.db", embedder=FixedEmbedder((1.0, 0.0, 0.0)))) as index:
        # Filler chunks push orthogonal keyword-only docs down in semantic ranking, as in a real corpus.
        fillers = [
            (
                make_chunk(f"filler{i}.md", "S", f"unrelated filler {i}", 0),
                np.array([0.5, 0.86, 0.0], dtype=np.float32),
            )
            for i in range(20)
        ]
        index._add_with_embeddings(
            [
                # Strong keyword matches, orthogonal semantically -> keyword #1, #2; semantic #24, #25
                (
                    make_chunk("kw1.md", "S", "amber amber amber amber", 0),
                    np.array([0.0, 1.0, 0.0], dtype=np.float32),
                ),
                (
                    make_chunk("kw2.md", "S", "amber amber amber", 0),
                    np.array([0.0, 1.0, 0.0], dtype=np.float32),
                ),
                # Strong semantic matches, no keyword match -> semantic #1, #2
                (
                    make_chunk("sem1.md", "S", "unrelated prose one", 0),
                    np.array([1.0, 0.0, 0.0], dtype=np.float32),
                ),
                (
                    make_chunk("sem2.md", "S", "unrelated prose two", 0),
                    np.array([0.99, 0.14, 0.0], dtype=np.float32),
                ),
                # #3 in BOTH legs -> RRF consensus winner (2/(k+3) > 1/(k+1) + 1/(k+24))
                (
                    make_chunk("both.md", "S", "a single mention of amber", 0),
                    np.array([0.95, 0.31, 0.0], dtype=np.float32),
                ),
                *fillers,
            ]
        )

        hits = index.search_hybrid("amber", limit=2)

        assert hits[0].chunk.version.path.name == "both.md"


def test_semantic_search_builds_chunks_only_for_walked_hits(tmp_path, make_chunk, monkeypatch):
    """Semantic search ranks by id + embedding and only hydrates chunks as `_take_shown` walks them (#257)."""
    import commonplace._search._sqlite as sqlite_mod

    # note0 ranks #1 but is deleted; note1 (#2) and note2 (#3) should fill limit=2 -> only 3 chunks hydrated.
    with closing(
        SQLiteSearchIndex(
            tmp_path / "index.db",
            embedder=FixedEmbedder((1.0, 0.0)),
            note_exists=lambda path: path.name != "note0.md",
        )
    ) as index:
        rows = [
            (
                make_chunk(f"note{i}.md", "S", f"Text {i}", 0),
                np.array([np.cos(i * 0.15), np.sin(i * 0.15)], dtype=np.float32),
            )
            for i in range(10)
        ]
        index._add_with_embeddings(rows)

        built = 0
        real_chunk = sqlite_mod.Chunk

        def spy_chunk(*args, **kwargs):
            nonlocal built
            built += 1
            return real_chunk(*args, **kwargs)

        monkeypatch.setattr(sqlite_mod, "Chunk", spy_chunk)

        hits = index._search_by_embedding(np.array([1.0, 0.0], dtype=np.float32), limit=2)

        assert [hit.chunk.version.path.name for hit in hits] == ["note1.md", "note2.md"]
        assert built == 3


def test_chunks_for_returns_counts_per_version_for_this_model_only(test_index, other_model_index, make_chunk):
    """Point lookup for one note's indexed versions: empty note, multi-chunk note, stale version, model-scoped (#322)."""
    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    old_id, cur_id = "1" * 40, "2" * 40

    assert test_index.chunks_for(Path("note.md")) == {}

    test_index.record_indexed([Version(Path("empty.md"), cur_id)])
    assert test_index.chunks_for(Path("empty.md")) == {cur_id: 0}

    test_index._add_with_embeddings(
        [
            (make_chunk("note.md", "S", "old", 0, content_id=old_id), emb),
            (make_chunk("note.md", "S", "first", 0, content_id=cur_id), emb),
            (make_chunk("note.md", "S", "second", 10, content_id=cur_id), emb),
        ]
    )
    other_model_index._add_with_embeddings([(make_chunk("note.md", "S", "other model", 0, content_id=cur_id), emb)])

    assert test_index.chunks_for(Path("note.md")) == {old_id: 1, cur_id: 2}


def test_sqlite_index_context_manager_closes_connection(tmp_path):
    """Exiting `with SQLiteSearchIndex(...)` closes its SQLite connection (#322)."""
    with SQLiteSearchIndex(tmp_path / "index.db", embedder=FixedEmbedder()) as index:
        assert index.chunks_for(Path("missing.md")) == {}

    with pytest.raises(sqlite3.ProgrammingError):
        index._conn.execute("SELECT 1")
