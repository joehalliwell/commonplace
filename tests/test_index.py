"""Tests for the index and search commands."""

from pathlib import Path

import pytest

from commonplace import _search
from commonplace._repo import Commonplace
from commonplace._types import Note


def test_index_rebuild(tmp_path):
    """Test the index function with rebuild flag."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add a test note
    note = Note(
        path=Path("test.md"),
        content="""# Test

Some content here.
""",
    )
    repo.save(note)

    db_path = repo_path / ".commonplace" / "embeddings.db"

    # Index first time
    _search.index(repo, db_path, rebuild=False)
    assert db_path.exists()

    # Rebuild
    _search.index(repo, db_path, rebuild=True)
    assert db_path.exists()


def test_search(tmp_path):
    """Test the search function."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add test notes with distinct content
    note1 = Note(
        path=Path("ml.md"),
        content="""# Machine Learning

## Introduction

Machine learning and neural networks are fascinating topics in AI.
""",
    )

    note2 = Note(
        path=Path("cooking.md"),
        content="""# Cooking

## Recipes

Baking bread requires flour, water, and yeast.
""",
    )

    repo.save(note1)
    repo.save(note2)
    repo.commit("Add test notes")

    db_path = repo_path / ".commonplace" / "embeddings.db"

    # Index the notes
    _search.index(repo, db_path)

    # Search for ML-related content
    results = _search.search(db_path, "artificial intelligence", limit=10)
    assert len(results) > 0
    # Should find the ML note
    assert any("ml.md" in str(hit.chunk.path) for hit in results)


def test_search_no_index(tmp_path):
    """Test search raises error when index doesn't exist."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    db_path = repo_path / ".commonplace" / "embeddings.db"

    with pytest.raises(FileNotFoundError, match="Index not found"):
        _search.search(db_path, "test query")


def test_search_with_limit(tmp_path):
    """Test search with limit parameter."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add multiple notes
    for i in range(5):
        note = Note(
            path=Path(f"note{i}.md"),
            content=f"""# Note {i}

Content for note {i}.
""",
        )
        repo.save(note)

    db_path = repo_path / ".commonplace" / "embeddings.db"

    # Index
    _search.index(repo, db_path)

    # Search with limit
    results = _search.search(db_path, "content", limit=3)
    assert len(results) <= 3


def test_index_incremental(tmp_path):
    """Test that index only indexes new notes when not rebuilding."""
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add first note
    note1 = Note(
        path=Path("first.md"),
        content="""# First Note

Initial content.
""",
    )
    repo.save(note1)
    repo.commit("Add first note")

    db_path = repo_path / ".commonplace" / "embeddings.db"

    # Index first time
    _search.index(repo, db_path, rebuild=False)

    # Verify first note is indexed
    from commonplace._search._store import SQLiteVectorStore

    store = SQLiteVectorStore(db_path)
    indexed_paths = store.get_indexed_paths()
    assert "first.md" in indexed_paths
    initial_count = len(indexed_paths)
    store.close()

    # Add second note
    note2 = Note(
        path=Path("second.md"),
        content="""# Second Note

More content.
""",
    )
    repo.save(note2)
    repo.commit("Add second note")

    # Index again without --rebuild (should only index the new note)
    _search.index(repo, db_path, rebuild=False)

    # Verify both notes are indexed
    store = SQLiteVectorStore(db_path)
    indexed_paths = store.get_indexed_paths()
    assert "first.md" in indexed_paths
    assert "second.md" in indexed_paths
    assert len(indexed_paths) == initial_count + 1
    store.close()

    # Run index again with no new notes - should be idempotent
    _search.index(repo, db_path, rebuild=False)

    store = SQLiteVectorStore(db_path)
    indexed_paths = store.get_indexed_paths()
    assert len(indexed_paths) == 2
    store.close()
