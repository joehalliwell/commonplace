"""Tests for the index and search commands."""

from pathlib import Path

import numpy as np

from commonplace._search import _commands
from commonplace._search._types import Chunk


def _delete(repo, path: str) -> None:
    """Delete a note the way a user would: remove it and commit the removal."""
    repo.remove(Path(path))
    repo.commit(f"Delete {path}", auto_index=False)


def test_search(test_repo, make_note):
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
    _commands.index(test_repo)

    # Search for ML-related content
    results = test_repo.index.search("artificial intelligence", limit=10)

    assert len(results) > 0
    # Should find the ML note
    assert any("ml.md" in str(hit.chunk.repo_path.path) for hit in results)


def test_search_with_limit(test_repo, make_note):
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
    _commands.index(test_repo)

    # Search with limit
    results = test_repo.index.search("content", limit=3)
    assert len(results) <= 3


def test_search_with_punctuation(test_repo, make_note):
    """Search queries containing commas and other FTS5 syntax don't crash."""
    note = make_note(
        path="test.md",
        content="# Test\n\nThinking about life, the universe, and everything.\n",
    )
    test_repo.save(note)
    test_repo.commit("Add test note")
    _commands.index(test_repo)

    # These queries contain FTS5 syntax characters (commas, parentheses)
    results = test_repo.index.search("life, the universe, and everything", limit=5)
    assert isinstance(results, list)

    results = test_repo.index.search("thinking (about) things", limit=5)
    assert isinstance(results, list)


def test_index_incremental(test_repo, make_note):
    """Test that index only indexes new notes when not rebuilding."""

    # Initially empty
    indexed_paths = set(test_repo.index.get_indexed_paths())
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
    _commands.index(test_repo)

    indexed_paths = set(test_repo.index.get_indexed_paths())
    assert test_repo.make_repo_path("first.md") in indexed_paths

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
    _commands.index(test_repo)

    # Verify both notes are indexed
    indexed_paths = set(test_repo.index.get_indexed_paths())
    assert test_repo.make_repo_path("first.md") in indexed_paths
    assert test_repo.make_repo_path("second.md") in indexed_paths

    # Index again without changes - should not add duplicates
    _commands.index(test_repo)
    assert set(test_repo.index.get_indexed_paths()) == indexed_paths


def test_search_hides_deleted_notes(test_repo, make_note):
    """A note deleted since the last index run is gone from results, index not yet pruned."""
    test_repo.save(make_note(path="doomed.md", content="# Doomed\n\nOzymandias king of kings.\n"))
    test_repo.commit("Add note", auto_index=False)
    _commands.index(test_repo)
    assert test_repo.index.search_keyword("Ozymandias", limit=10)

    _delete(test_repo, "doomed.md")

    assert test_repo.index.search_keyword("Ozymandias", limit=10) == []
    assert [
        hit for hit in test_repo.index.search("Ozymandias", limit=10) if hit.chunk.repo_path.path.name == "doomed.md"
    ] == []


def test_search_include_deleted_shows_them(test_repo, make_note):
    """The index still holds the chunks, so --include-deleted can reach them."""
    test_repo.save(make_note(path="doomed.md", content="# Doomed\n\nOzymandias king of kings.\n"))
    test_repo.commit("Add note", auto_index=False)
    _commands.index(test_repo)

    _delete(test_repo, "doomed.md")

    hits = test_repo.index.search_keyword("Ozymandias", limit=10, include_deleted=True)
    assert [str(hit.chunk.repo_path.path) for hit in hits] == ["doomed.md"]


def test_search_keeps_finding_an_edited_note(test_repo, make_note):
    """An edited note stays in results on its old chunks until the index catches up.

    The note is still there to open, so a stale quote costs the reader less than
    the note vanishing from search between the edit and the next index run. Only
    deletion hides a hit.
    """
    test_repo.save(make_note(path="draft.md", content="# Draft\n\nHerrings are silver.\n"))
    test_repo.commit("Add note", auto_index=False)
    _commands.index(test_repo)

    test_repo.save(make_note(path="draft.md", content="# Draft\n\nHerrings are crimson.\n"))
    test_repo.commit("Edit note", auto_index=False)

    hits = test_repo.index.search_keyword("silver", limit=10)
    assert [str(hit.chunk.repo_path.path) for hit in hits] == ["draft.md"]


def test_search_fills_the_limit_around_deleted_notes(test_repo, make_note):
    """Filtering happens while walking the ranking, so hidden hits don't eat the limit."""
    for i in range(5):
        test_repo.save(make_note(path=f"note{i}.md", content=f"# Note {i}\n\nHerrings are silver, number {i}.\n"))
    test_repo.commit("Add notes", auto_index=False)
    _commands.index(test_repo)

    _delete(test_repo, "note0.md")
    _delete(test_repo, "note1.md")

    assert len(test_repo.index.search_keyword("herrings", limit=3)) == 3
    assert len(test_repo.index.search_semantic("herrings", limit=3)) == 3


def test_index_rebuild_reindexes_everything(test_repo, make_note):
    """A rebuild clears first, so every live note has to come back on the same run."""
    test_repo.save(make_note(path="one.md", content="# One\n\nFirst note.\n"))
    test_repo.save(make_note(path="two.md", content="# Two\n\nSecond note.\n"))
    test_repo.commit("Add notes", auto_index=False)
    _commands.index(test_repo)
    indexed = set(test_repo.index.get_indexed_paths())
    assert {Path("one.md"), Path("two.md")} <= {p.path for p in indexed}

    _commands.index(test_repo, rebuild=True)

    assert set(test_repo.index.get_indexed_paths()) == indexed


def test_index_prunes_deleted_notes(test_repo, make_note):
    """A note deleted from the repo leaves the index on the next run."""
    test_repo.save(make_note(path="doomed.md", content="# Doomed\n\nNot long for this world.\n"))
    test_repo.commit("Add note", auto_index=False)
    _commands.index(test_repo)
    assert set(test_repo.index.get_indexed_paths())

    _delete(test_repo, "doomed.md")
    _commands.index(test_repo)

    assert Path("doomed.md") not in {p.path for p in test_repo.index.get_indexed_paths()}


def test_index_commonplace_dir_pruned(test_repo, make_note):
    """A chunk indexed from .commonplace/ before it was excluded leaves on the next run."""
    test_repo.save(make_note(path=".commonplace/skills/rake/chaff.md", content="# Chaff\n\nDropped in triage.\n"))
    test_repo.commit("Add chaff", auto_index=False)
    stale = test_repo.make_repo_path(".commonplace/skills/rake/chaff.md")
    chunk = Chunk(repo_path=stale, section="Chaff", text="Dropped in triage.", offset=0)
    test_repo.index._add_with_embedding(chunk, np.array([1.0, 0.0, 0.0], dtype=np.float32))

    _commands.index(test_repo)

    assert stale not in set(test_repo.index.get_indexed_paths())


def test_index_reembeds_only_the_chunks_an_edit_changed(test_repo, make_note, monkeypatch):
    """A new commit makes the whole note new to the index; unchanged chunks keep their embeddings."""
    body = "# Draft\n\n## Herrings\n\nHerrings are silver.\n\n## Sprats\n\nSprats are small.\n"
    test_repo.save(make_note(path="draft.md", content=body))
    test_repo.commit("Add note", auto_index=False)
    _commands.index(test_repo)
    embedded: list[str] = []
    embed_docs = test_repo.index._embedder.embed_docs
    monkeypatch.setattr(
        test_repo.index._embedder, "embed_docs", lambda texts: embedded.extend(texts) or embed_docs(texts)
    )

    test_repo.save(make_note(path="draft.md", content=body.replace("small", "tiny")))
    test_repo.commit("Edit one section", auto_index=False)
    _commands.index(test_repo)

    assert len(embedded) == 1 and "tiny" in embedded[0]
    assert test_repo.index.search_keyword("silver", limit=10)


def test_index_prunes_superseded_versions(test_repo, make_note):
    """Editing a note replaces its chunks rather than accumulating a version per edit."""
    test_repo.save(make_note(path="draft.md", content="# Draft\n\nHerrings are silver.\n"))
    test_repo.commit("Add note", auto_index=False)
    _commands.index(test_repo)

    test_repo.save(make_note(path="draft.md", content="# Draft\n\nHerrings are crimson.\n"))
    test_repo.commit("Edit note", auto_index=False)
    _commands.index(test_repo)

    drafts = [p for p in test_repo.index.get_indexed_paths() if p.path == Path("draft.md")]
    assert drafts == [test_repo.make_repo_path("draft.md")]
    assert test_repo.index.search_keyword("crimson", limit=10)
    assert test_repo.index.search_keyword("silver", limit=10) == []


def test_index_no_prune_keeps_deleted_notes(test_repo, make_note):
    """`--no-prune` leaves the index alone, for when re-embedding would cost more than the noise."""
    test_repo.save(make_note(path="doomed.md", content="# Doomed\n\nNot long for this world.\n"))
    test_repo.commit("Add note", auto_index=False)
    _commands.index(test_repo)
    indexed = set(test_repo.index.get_indexed_paths())

    _delete(test_repo, "doomed.md")
    _commands.index(test_repo, prune=False)

    assert set(test_repo.index.get_indexed_paths()) == indexed
