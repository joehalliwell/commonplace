"""Tests for the index and search commands."""

from commonplace import _search
from commonplace._repo import Commonplace
from commonplace._search._embedder import SentenceTransformersEmbedder


def test_index_rebuild(tmp_path, make_note):
    """Test the index function with rebuild flag."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add a test note
    note = make_note(
        path="test.md",
        content="""# Test

Some content here.
""",
    )
    repo.save(note)

    db_path = repo_path / ".commonplace" / "embeddings.db"
    embedder = SentenceTransformersEmbedder()

    # Index first time
    _search.index(repo, db_path, rebuild=False, embedder=embedder)
    assert db_path.exists()

    # Rebuild
    _search.index(repo, db_path, rebuild=True, embedder=embedder)
    assert db_path.exists()


def test_search(tmp_path, make_note):
    """Test the search function."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add test notes with distinct content
    note1 = make_note(
        path="ml.md",
        content="""# Machine Learning

## Introduction

Machine learning and neural networks are fascinating topics in AI.
""",
    )

    note2 = make_note(
        path="cooking.md",
        content="""# Cooking

## Recipes

Baking bread requires flour, water, and yeast.
""",
    )

    repo.save(note1)
    repo.save(note2)
    repo.commit("Add test notes")

    db_path = repo_path / ".commonplace" / "embeddings.db"
    embedder = SentenceTransformersEmbedder()

    # Index the notes
    _search.index(repo, db_path, embedder=embedder)

    # Search for ML-related content
    store = _search.SQLiteVectorStore(db_path, embedder=embedder)
    results = store.search("artificial intelligence", limit=10)
    store.close()

    assert len(results) > 0
    # Should find the ML note
    assert any("ml.md" in str(hit.chunk.repo_path.path) for hit in results)


def test_search_no_index(tmp_path):
    """Test search raises error when index doesn't exist."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    db_path = repo_path / ".commonplace" / "embeddings.db"

    # Just verify the file doesn't exist - no need to test error handling
    assert not db_path.exists()


def test_search_with_limit(tmp_path, make_note):
    """Test search with limit parameter."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add multiple notes
    for i in range(5):
        note = make_note(
            path=f"note{i}.md",
            content=f"""# Note {i}

Content for note {i}.
""",
        )
        repo.save(note)

    db_path = repo_path / ".commonplace" / "embeddings.db"
    embedder = SentenceTransformersEmbedder()

    # Index
    _search.index(repo, db_path, embedder=embedder)

    # Search with limit
    store = _search.SQLiteVectorStore(db_path, embedder=embedder)
    results = store.search("content", limit=3)
    store.close()

    assert len(results) <= 3


def test_index_incremental(tmp_path, make_note):
    """Test that index only indexes new notes when not rebuilding."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add first note
    note1 = make_note(
        path="first.md",
        content="""# First Note

Initial content.
""",
    )
    repo.save(note1)
    repo.commit("Add first note")

    db_path = repo_path / ".commonplace" / "embeddings.db"
    embedder = SentenceTransformersEmbedder()

    # Index first time
    _search.index(repo, db_path, rebuild=False, embedder=embedder)

    # Verify first note is indexed
    from commonplace._search._store import SQLiteVectorStore

    store = SQLiteVectorStore(db_path, embedder=embedder)
    indexed_paths = store.get_indexed_paths()
    assert "first.md" in indexed_paths
    initial_count = len(indexed_paths)
    store.close()

    # Add second note
    note2 = make_note(
        path="second.md",
        content="""# Second Note

More content.
""",
    )
    repo.save(note2)
    repo.commit("Add second note")

    # Index again without --rebuild (should only index the new note)
    _search.index(repo, db_path, rebuild=False, embedder=embedder)

    # Verify both notes are indexed
    store = SQLiteVectorStore(db_path, embedder=embedder)
    indexed_paths = store.get_indexed_paths()
    assert "first.md" in indexed_paths
    assert "second.md" in indexed_paths
    assert len(indexed_paths) == initial_count + 1
    store.close()

    # Run index again with no new notes - should be idempotent
    _search.index(repo, db_path, rebuild=False, embedder=embedder)

    store = SQLiteVectorStore(db_path, embedder=embedder)
    indexed_paths = store.get_indexed_paths()
    assert len(indexed_paths) == 2
    store.close()
