"""The graph in the index: each version of a file, committed or not, is read once, and its edges land again as files
come and go."""

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

from commonplace import _types
from commonplace._cache import INDEX_DB, INDEX_VERSION
from commonplace._graph import GraphStore, Half
from commonplace._links import Files, Target
from commonplace._marginalia import marginalia_path
from commonplace._repo import Commonplace
from commonplace._search import _commands
from tests.porcelain import git

IDEAS, OTHER = Path("notes/ideas.md"), Path("notes/other.md")


def commit(repo: Commonplace, files: dict[str, str] | None = None) -> None:
    for path, text in (files or {}).items():
        (repo.root / path).parent.mkdir(parents=True, exist_ok=True)
        (repo.root / path).write_text(text)
    git(repo.root, "add", "-A")
    git(repo.root, "commit", "-qm", "notes")


def linking(repo: Commonplace, path: Path) -> list[str]:
    """Which notes link to `path`, as a fresh process finds them."""
    with Commonplace.open(repo.root).graph() as graph:
        return [str(edge.node) for edge in graph.in_edges(path)]


def unreadable(*_, **__):
    raise AssertionError("parsed a file the cache holds")


def stored(repo: Commonplace, query: str) -> list[tuple]:
    with closing(sqlite3.connect(repo.root / INDEX_DB)) as db:
        return db.execute(query).fetchall()


def test_graph_cache_second_pass_parses_neither_half_of_a_committed_node(test_repo, monkeypatch):
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): "", str(OTHER): ""})
    test_repo.add_link(OTHER, Target(IDEAS), "why", on=date(2026, 11, 24))
    commit(test_repo)
    assert linking(test_repo, IDEAS) == ["journal/a.md", "notes/other.md"]

    monkeypatch.setattr("commonplace._types.extract_links", unreadable)

    assert linking(test_repo, IDEAS) == ["journal/a.md", "notes/other.md"]


def test_graph_cache_uncommitted_note_and_marginalia_are_read_afresh(test_repo):
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): "", str(OTHER): ""})
    assert linking(test_repo, IDEAS) == ["journal/a.md"]

    (test_repo.root / "journal/a.md").write_text("See [[other]].\n")
    test_repo.add_link(OTHER, Target(IDEAS), "why", on=date(2026, 11, 24))

    assert (linking(test_repo, IDEAS), linking(test_repo, OTHER)) == (["notes/other.md"], ["journal/a.md"])


def test_graph_cache_lands_edges_again_when_the_files_change(test_repo, monkeypatch):
    """Where a link lands depends on every other file, so a note appearing moves an edge its own file never changed."""
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n"})
    assert linking(test_repo, IDEAS) == []
    extract = _types.extract_links

    def unless_linking(text: str, *, source: Path, **kwargs) -> list:
        assert source != Path("journal/a.md"), "read journal/a.md again"
        return extract(text, source=source, **kwargs)

    monkeypatch.setattr("commonplace._types.extract_links", unless_linking)

    commit(test_repo, {str(IDEAS): ""})

    assert linking(test_repo, IDEAS) == ["journal/a.md"]


def test_graph_cache_uncommitted_file_is_read_once_per_version(test_repo, monkeypatch):
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): "", str(OTHER): ""})
    (test_repo.root / "journal/a.md").write_text("See [[other]].\n")
    assert linking(test_repo, OTHER) == ["journal/a.md"]

    monkeypatch.setattr("commonplace._types.extract_links", unreadable)

    assert linking(test_repo, OTHER) == ["journal/a.md"]


def test_graph_cache_full_pass_keeps_only_files_still_committed(test_repo):
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): ""})
    linking(test_repo, IDEAS)
    commit(test_repo, {"journal/a.md": "See [[ideas]] again.\n"})

    linking(test_repo, IDEAS)

    versions = set(stored(test_repo, "SELECT path, content_id FROM graph_files"))
    ids = test_repo.content_ids()
    assert versions == {(str(path), ids[path]) for path in test_repo.note_paths()}


def test_index_stores_new_notes_contributions_and_keeps_the_rest(test_repo, monkeypatch):
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): ""})
    linking(test_repo, IDEAS)
    commit(test_repo, {"journal/b.md": "---\ntags: [tea]\n---\n\nAnd [[ideas]].\n"})

    _commands.index(test_repo)
    monkeypatch.setattr("commonplace._types.extract_links", unreadable)

    assert linking(test_repo, IDEAS) == ["journal/a.md", "journal/b.md"]
    assert stored(test_repo, "SELECT label FROM graph_labels") == [("tea",)]


def test_index_of_an_edited_note_leaves_every_other_edge_landed(test_repo, monkeypatch):
    """The file set didn't change, so only the new version's edges need landing."""
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", "journal/b.md": "And [[ideas]].\n", str(IDEAS): ""})
    linking(test_repo, IDEAS)
    commit(test_repo, {"journal/b.md": "And [[ideas]] again.\n"})
    _commands.index(test_repo)
    landed: list[Path] = []
    land = Files.landing
    monkeypatch.setattr(Files, "landing", lambda self, edge: landed.append(edge.node) or land(self, edge))

    assert linking(test_repo, IDEAS) == ["journal/a.md", "journal/b.md"]
    assert set(landed) == {Path("journal/b.md")}


def test_uncommitted_file_whose_name_starts_with_a_quote_is_read(test_repo):
    commit(test_repo, {str(IDEAS): ""})
    (test_repo.root / 'journal/"quoted".md').parent.mkdir(parents=True, exist_ok=True)
    (test_repo.root / 'journal/"quoted".md').write_text("See [[ideas]].\n")

    assert linking(test_repo, IDEAS) == ['journal/"quoted".md']


def test_warm_pass_writes_nothing_so_waits_on_no_writer(test_repo):
    """WAL lets readers run beside a writer such as `index`; a pass with nothing new must stay a reader."""
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): ""})
    linking(test_repo, IDEAS)

    with closing(sqlite3.connect(test_repo.root / INDEX_DB, timeout=0.1)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        assert linking(test_repo, IDEAS) == ["journal/a.md"]


def test_two_processes_storing_the_same_version_at_once_both_succeed(test_repo):
    """Warm passes read before writing, so two cold ones may both find a version missing; the second must not fail."""
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): ""})
    key = ("journal/a.md", test_repo.content_ids()[Path("journal/a.md")])
    half = Half([], [])
    with GraphStore(test_repo.root / INDEX_DB) as first, GraphStore(test_repo.root / INDEX_DB) as second:

        def read_while_another_stores(_: tuple[str, str]) -> Half:
            first.sync([key], lambda _: half, False, None)
            return half

        second.sync([key], read_while_another_stores, False, None)

    assert stored(test_repo, "SELECT COUNT(*) FROM graph_files") == [(1,)]


def test_graph_labels_come_warm_from_the_cache_own_then_marginalia_each_once(test_repo, monkeypatch):
    commit(test_repo, {str(IDEAS): "---\ntags: [tea, drink]\n---\n"})
    test_repo.label(IDEAS, "tea", "later")
    commit(test_repo)
    with Commonplace.open(test_repo.root).graph() as graph:
        assert graph.labels(IDEAS, marginalia_path(IDEAS)) == ["tea", "drink", "later"]

    monkeypatch.setattr("commonplace._repo.read_marginalia", unreadable)
    monkeypatch.setattr(Commonplace, "_read_note", unreadable)

    with Commonplace.open(test_repo.root).graph() as graph:
        assert graph.labels(IDEAS, marginalia_path(IDEAS)) == ["tea", "drink", "later"]


def test_check_sees_a_heading_go_though_no_file_came_or_went(test_repo):
    """A span is checked against the note as it stands, so a cached edge to it can still break."""
    commit(test_repo, {"journal/a.md": "See [[ideas#Tea]].\n", str(IDEAS): "## Tea\n"})
    assert Commonplace.open(test_repo.root).check() == []

    (test_repo.root / IDEAS).write_text("## Coffee\n")

    assert [broken.reason for broken in Commonplace.open(test_repo.root).check()] == ["no such heading or phrase"]


@pytest.mark.parametrize(
    "change", [{"remove": str(IDEAS)}, {"add": "notes/b/ideas.md"}], ids=["target deleted", "target duplicated"]
)
def test_an_edge_lands_nowhere_once_its_target_is_gone_or_has_a_namesake(test_repo, change):
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): ""})
    assert linking(test_repo, IDEAS) == ["journal/a.md"]

    if "remove" in change:
        (test_repo.root / change["remove"]).unlink()
        commit(test_repo)
    else:
        commit(test_repo, {change["add"]: ""})

    assert linking(test_repo, IDEAS) == []
    assert stored(test_repo, "SELECT to_node FROM graph_edges WHERE from_node = 'journal/a.md'") == [(None,)]


def test_a_gone_notes_marginalia_still_link(test_repo):
    """A note whose file went keeps what was said about it, links included."""
    commit(test_repo, {str(IDEAS): "", str(OTHER): ""})
    test_repo.add_link(OTHER, Target(IDEAS), "why", on=date(2026, 11, 24))
    (test_repo.root / OTHER).unlink()
    commit(test_repo)

    assert linking(test_repo, IDEAS) == ["notes/other.md"]


def test_index_rebuild_rereads_the_graph_as_rebuild_graph_does(test_repo):
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): "", str(OTHER): ""})
    linking(test_repo, IDEAS)
    with closing(sqlite3.connect(test_repo.root / INDEX_DB)) as db, db:
        db.execute("UPDATE graph_edges SET to_node = 'notes/other.md' WHERE from_node = 'journal/a.md'")

    _commands.index(test_repo, rebuild=True)

    assert (linking(test_repo, IDEAS), linking(test_repo, OTHER)) == (["journal/a.md"], [])


def test_index_rebuild_graph_rereads_what_the_cache_holds(test_repo):
    """How a fix to link parsing reaches notes committed before it."""
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): "", str(OTHER): ""})
    linking(test_repo, IDEAS)
    with closing(sqlite3.connect(test_repo.root / INDEX_DB)) as db, db:
        db.execute(
            "UPDATE graph_edges SET target = 'other', to_node = 'notes/other.md' WHERE from_node = 'journal/a.md'"
        )
    assert linking(test_repo, OTHER) == ["journal/a.md"]

    _commands.index(test_repo, rebuild_graph=True)

    assert (linking(test_repo, IDEAS), linking(test_repo, OTHER)) == (["journal/a.md"], [])


def test_graph_newer_than_this_release_is_refused(test_repo):
    """As the search index is: what a newer release wrote, this one can't know it reads right."""
    commit(test_repo, {"journal/a.md": "See [[ideas]].\n", str(IDEAS): ""})
    (test_repo.root / INDEX_DB).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(test_repo.root / INDEX_DB)) as db:
        db.execute(f"PRAGMA user_version = {INDEX_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer"):
        linking(test_repo, IDEAS)
