"""Every index schema version we have ever written, against the committed examples in tests/resources/index/.

`any_index_version` is parametrised over the full range, so a bump without a matching example fails
rather than going untested. Every example holds the same chunks, which is what lets each test say the
guarantee: an index any earlier release wrote still opens to the same thing.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from commonplace._search._sqlite import INDEX_VERSION, SQLiteSearchIndex
from commonplace._types import RepoPath
from tests.resources.index.make_examples import REF_A, REF_B, ExampleEmbedder

TEA = RepoPath(Path("notes/tea.md"), REF_A)
WALKS = RepoPath(Path("notes/walks.md"), REF_B)


def _open(example):
    return closing(SQLiteSearchIndex(example.path, embedder=ExampleEmbedder()))


def _found(hits) -> list[tuple[str, int]]:
    return [(str(hit.chunk.repo_path.path), hit.chunk.offset) for hit in hits]


def test_every_index_version_lists_the_same_notes(any_index_version):
    with _open(any_index_version) as index:
        assert set(index.get_indexed_paths()) == {TEA, WALKS}


def test_every_index_version_finds_by_keyword(any_index_version):
    with _open(any_index_version) as index:
        assert _found(index.search_keyword("river")) == [("notes/walks.md", 0)]


def test_every_index_version_ranks_by_its_stored_embeddings(any_index_version):
    with _open(any_index_version) as index:
        assert _found(index.search_semantic("Steep for four minutes.", limit=1)) == [("notes/tea.md", 40)]


def test_every_index_version_counts_chunks_per_note(any_index_version):
    with _open(any_index_version) as index:
        assert {stat.repo_path: stat.num_chunks for stat in index.stats()} == {TEA: 2, WALKS: 1}


def _schema(db: Path) -> dict[str, list[tuple]]:
    """Each table, index and trigger SQLite holds, with a table's columns, so two databases compare by shape."""
    with closing(sqlite3.connect(db)) as conn:
        names = conn.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name")
        return {
            f"{kind} {name}": conn.execute(f"PRAGMA table_info({name})").fetchall() if kind == "table" else []
            for kind, name in names.fetchall()
        }


def _user_version(db: Path) -> int:
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def test_every_index_version_opens_with_the_schema_of_a_fresh_index(any_index_version, tmp_path):
    """A migration that drifted from the fresh DDL would leave old indexes subtly different for good."""
    with _open(any_index_version):
        pass
    with closing(SQLiteSearchIndex(tmp_path / "fresh.db", embedder=ExampleEmbedder())):
        pass

    assert _schema(any_index_version.path) == _schema(tmp_path / "fresh.db")
    assert _user_version(any_index_version.path) == _user_version(tmp_path / "fresh.db") == INDEX_VERSION


def test_an_index_newer_than_this_release_is_refused(tmp_path):
    """Its schema is unknown here, so reading or writing it could only do harm."""
    db = tmp_path / "index.db"
    with closing(sqlite3.connect(db)) as conn:
        conn.execute(f"PRAGMA user_version = {INDEX_VERSION + 1}")

    with pytest.raises(RuntimeError, match=str(db)):
        SQLiteSearchIndex(db, embedder=ExampleEmbedder())


def test_every_index_version_removes_a_note_from_keyword_search_too(any_index_version):
    with _open(any_index_version) as index:
        index.remove([WALKS])

        assert set(index.get_indexed_paths()) == {TEA}
        assert index.search_keyword("river") == []
    # Searches join through notes, so they would hide orphaned chunks: count what's actually left.
    with closing(sqlite3.connect(any_index_version.path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM chunks_fts_docsize").fetchone()[0] == 2
