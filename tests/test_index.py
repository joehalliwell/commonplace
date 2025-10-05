"""Tests for the index and search commands."""

from commonplace._search import _commands


def test_search(test_repo, test_store, make_note):
    """Test the search function."""
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

    test_repo.save(note1)
    test_repo.save(note2)
    test_repo.commit("Add test notes")

    # Index the notes
    _commands.index(test_repo, test_store)

    # Search for ML-related content
    results = test_store.search("artificial intelligence", limit=10)

    assert len(results) > 0
    # Should find the ML note
    assert any("ml.md" in str(hit.chunk.repo_path.path) for hit in results)


def test_search_with_limit(test_repo, test_store, make_note):
    """Test search with limit parameter."""
    # Add multiple notes
    for i in range(5):
        note = make_note(
            path=f"note{i}.md",
            content=f"""# Note {i}

Content for note {i}.
""",
        )
        test_repo.save(note)

    # Index
    _commands.index(test_repo, test_store)

    # Search with limit
    results = test_store.search("content", limit=3)
    assert len(results) <= 3


def test_index_incremental(test_repo, test_store, make_note):
    """Test that index only indexes new notes when not rebuilding."""

    # Initially empty
    indexed_paths = set(test_store.get_indexed_paths())
    assert len(indexed_paths) == 0

    # Add first note
    note1 = make_note(
        path="first.md",
        content="""# First Note

Initial content.
""",
    )
    test_repo.save(note1)
    test_repo.commit("Add first note")

    # Index
    _commands.index(test_repo, test_store)

    indexed_paths = set(test_store.get_indexed_paths())
    assert test_repo.make_repo_path("first.md") in indexed_paths
    assert len(indexed_paths) == 1

    # Add second note
    note2 = make_note(
        path="second.md",
        content="""# Second Note

More content.
""",
    )
    test_repo.save(note2)
    test_repo.commit("Add second note")

    # Index
    _commands.index(test_repo, test_store)

    # Verify both notes are indexed
    indexed_paths = set(test_store.get_indexed_paths())
    assert test_repo.make_repo_path("first.md") in indexed_paths
    assert test_repo.make_repo_path("second.md") in indexed_paths
    assert len(indexed_paths) == 3

    # Index
    _commands.index(test_repo, test_store)
    indexed_paths = set(test_store.get_indexed_paths())
    assert len(indexed_paths) == 3
