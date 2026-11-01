"""Tests for marginalia: what's been said about a note since, kept in a shadow tree beside it."""

import shutil
from datetime import date
from pathlib import Path

import pytest

from commonplace._links import UnresolvedNote
from commonplace._marginalia import (
    MARGINALIA_VERSION,
    Sidecar,
    backlinks,
    link,
    read_sidecar,
    sidecar_path,
    tag,
    unlink,
    untag,
    write_sidecar,
)
from commonplace._utils import load_frontmatter
from tests.porcelain import git

EXAMPLES = Path(__file__).parent / "resources" / "marginalia"
NODE = Path("notes/ideas.md")


@pytest.fixture
def notes(test_repo, make_note):
    """A repo with a few committed notes."""
    for path in ("notes/ideas.md", "chats/claude-tasks/2026/10/log.md", "chats/claude-tasks/2026/11/log.md"):
        test_repo.save(make_note(path=path, content=f"# {path}\n\nSome text.\n"))
    test_repo.commit("Add notes", auto_index=False)
    return test_repo


@pytest.fixture
def as_joe(monkeypatch):
    """Joe's identity, as git would find it in his config."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Joe")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "joe@example.com")


@pytest.fixture(params=range(1, MARGINALIA_VERSION + 1), ids=lambda v: f"marginalia-v{v}")
def any_marginalia_version(request, tmp_path) -> Path:
    """A repo root holding one example sidecar per format version, all for `NODE` with the same content."""
    source = EXAMPLES / f"v{request.param}.md"
    if not source.exists():
        pytest.fail(f"marginalia v{request.param} has no example at {source} — add one with the version bump")
    target = tmp_path / sidecar_path(NODE)
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    return tmp_path


def test_every_marginalia_version_reads_to_the_same_sidecar(any_marginalia_version):
    sidecar = read_sidecar(any_marginalia_version, NODE)

    assert sidecar.tags == ["hidden", "tea"]
    assert "[[/notes/todo]]" in sidecar.body


def test_a_note_without_a_sidecar_reads_as_untagged(tmp_path):
    assert read_sidecar(tmp_path, NODE) == Sidecar(node=NODE)


def test_a_sidecar_lives_at_the_notes_path_in_the_shadow_tree():
    assert sidecar_path(Path("chats/claude/2026/06/tea.md")) == Path(
        ".commonplace/marginalia/chats/claude/2026/06/tea.md"
    )


def test_tags_round_trip_through_the_shadow_tree(test_repo):
    write_sidecar(test_repo, Sidecar(node=NODE).tagged("hidden", "tea"))

    assert read_sidecar(test_repo.root, NODE).tags == ["hidden", "tea"]
    metadata, _ = load_frontmatter((test_repo.root / sidecar_path(NODE)).read_text())
    assert metadata["marginalia"] == MARGINALIA_VERSION


def test_tagging_again_with_a_tag_it_has_adds_nothing():
    assert Sidecar(node=NODE).tagged("tea").tagged("tea", "hidden").tags == ["tea", "hidden"]


def test_untagging_leaves_the_body_alone():
    """The body is the log, appended to and never rewritten by tag changes."""
    sidecar = Sidecar(node=NODE, tags=["tea", "hidden"], body="- 2026-11-01 filed as [[/notes/todo]]\n")

    assert sidecar.untagged("hidden") == Sidecar(node=NODE, tags=["tea"], body=sidecar.body)


def test_tag_records_the_tags_and_the_notes_ref(notes, as_joe):
    tag(notes, "ideas", ["hidden", "tea"])

    sidecar = read_sidecar(notes.root, NODE)
    assert sidecar.tags == ["hidden", "tea"]
    assert sidecar.ref == notes.make_repo_path(NODE).ref


def test_tag_commits_as_the_person_not_the_bot(notes, as_joe):
    """Tools tell a person's tags from their own by the commit's author, so they never remove them."""
    tag(notes, "ideas", ["hidden"])

    assert git(notes.root, "log", "-1", "--format=%an") == "Joe\n"


def test_tag_a_glob_tags_every_match(notes, as_joe):
    tag(notes, "/chats/claude-tasks/**", ["scheduled"])

    for month in ("10", "11"):
        assert read_sidecar(notes.root, Path(f"chats/claude-tasks/2026/{month}/log.md")).tags == ["scheduled"]


def test_untag_removes_only_the_tags_named(notes, as_joe):
    tag(notes, "ideas", ["hidden", "tea"])

    untag(notes, "ideas", ["hidden"])

    assert read_sidecar(notes.root, NODE).tags == ["tea"]


def test_tag_a_span_is_refused(notes, as_joe):
    """Tags describe whole notes; only edges reach inside one."""
    with pytest.raises(UnresolvedNote, match="whole notes"):
        tag(notes, "ideas#Tea house", ["hidden"])


def test_tag_cli_shows_a_notes_tags_when_given_none(notes, as_joe, test_app, capsys):
    assert test_app(["tag", "ideas", "hidden", "tea"]) == 0
    capsys.readouterr()

    assert test_app(["tag", "ideas"]) == 0

    assert capsys.readouterr().out.split() == ["hidden", "tea"]


def test_every_wikilink_in_a_sidecar_body_is_an_edge_from_its_note(any_marginalia_version):
    """Free prose links count too: 'filed as [[/notes/todo]]' says something about this note."""
    assert read_sidecar(any_marginalia_version, NODE).edges == ["/notes/todo"]


def test_link_to_an_ambiguous_name_fails_and_writes_nothing(notes, as_joe):
    with pytest.raises(UnresolvedNote):  # Two notes are called log
        link(notes, "ideas", "log", "")

    assert read_sidecar(notes.root, NODE) == Sidecar(node=NODE)


def test_link_records_the_edge_and_commits_as_the_person(notes, as_joe):
    link(notes, "ideas", '2026/10/log#"Some text."', "the same thought, scheduled", on=date(2026, 11, 2))

    sidecar = read_sidecar(notes.root, NODE)
    assert sidecar.body.splitlines() == [
        '- 2026-11-02 [[/chats/claude-tasks/2026/10/log#"Some text."]] the same thought, scheduled'
    ]
    assert sidecar.edges == ['/chats/claude-tasks/2026/10/log#"Some text."']
    assert git(notes.root, "log", "-1", "--format=%an") == "Joe\n"


def test_link_keeps_the_tags_and_appends_after_whats_there(notes, as_joe):
    tag(notes, "ideas", ["tea"])
    link(notes, "ideas", "2026/10/log", "", on=date(2026, 11, 2))
    link(notes, "ideas", "2026/11/log", "and again", on=date(2026, 11, 3))

    sidecar = read_sidecar(notes.root, NODE)
    assert sidecar.tags == ["tea"]
    assert sidecar.edges == ["/chats/claude-tasks/2026/10/log", "/chats/claude-tasks/2026/11/log"]


def test_link_from_a_span_is_refused(notes, as_joe):
    """A sidecar speaks for a whole note; the span belongs at the other end."""
    with pytest.raises(UnresolvedNote, match="whole notes"):
        link(notes, "ideas#Something", "2026/10/log", "")


def test_unlink_removes_only_the_edges_to_that_target(notes, as_joe):
    link(notes, "ideas", "2026/10/log", "", on=date(2026, 11, 2))
    link(notes, "ideas", "2026/11/log", "", on=date(2026, 11, 2))

    assert unlink(notes, "ideas", "2026/10/log") == 1

    assert read_sidecar(notes.root, NODE).edges == ["/chats/claude-tasks/2026/11/log"]


def test_unlink_an_edge_that_isnt_there_fails(notes, as_joe):
    with pytest.raises(ValueError, match="no link"):
        unlink(notes, "ideas", "2026/10/log")


def test_unlink_a_link_whose_target_is_gone_by_writing_it_as_the_sidecar_does(notes, as_joe):
    """doctor reports dead links; they must stay removable once their note can no longer be named."""
    link(notes, "ideas", "2026/10/log", "", on=date(2026, 11, 2))
    notes.remove(Path("chats/claude-tasks/2026/10/log.md"))
    notes.commit("Delete", auto_index=False)

    with pytest.raises(UnresolvedNote, match="/chats/claude-tasks/2026/10/log"):  # The hint shows how
        unlink(notes, "ideas", "2026/10/log")
    assert unlink(notes, "ideas", "[[/chats/claude-tasks/2026/10/log]]") == 1

    assert read_sidecar(notes.root, NODE).edges == []


def test_link_cli_takes_the_rest_of_the_line_as_why(notes, as_joe, test_app):
    assert test_app(["link", "ideas", "2026/10/log", "filed", "as", "an", "idea"]) == 0

    [line] = read_sidecar(notes.root, NODE).body.splitlines()
    assert line.endswith("[[/chats/claude-tasks/2026/10/log]] filed as an idea")


def test_backlinks_gather_marginalia_edges_and_links_in_notes(notes, as_joe, make_note):
    notes.save(make_note(path="journal/2026-11-02.md", content="# Day\n\nAdded to [[ideas]].\n"))
    notes.commit("Journal", auto_index=False)
    link(notes, "2026/10/log", 'ideas#"Some text."', "the same thought", on=date(2026, 11, 2))

    found = {(str(b.source), b.context) for b in backlinks(notes, "ideas")}

    assert found == {
        ("chats/claude-tasks/2026/10/log.md", '- 2026-11-02 [[/notes/ideas#"Some text."]] the same thought'),
        ("journal/2026-11-02.md", "line 3"),
    }


def test_backlinks_leave_out_hidden_sources_unless_asked(notes, as_joe):
    link(notes, "2026/10/log", "ideas", "", on=date(2026, 11, 2))
    tag(notes, "2026/10/log", ["hidden"])

    assert backlinks(notes, "ideas") == []
    assert len(backlinks(notes, "ideas", include_hidden=True)) == 1


def test_backlinks_cli_prints_each_source_rooted(notes, as_joe, test_app, capsys):
    link(notes, "2026/10/log", "ideas", "filed", on=date(2026, 11, 2))
    capsys.readouterr()

    assert test_app(["backlinks", "ideas"]) == 0

    assert capsys.readouterr().out == "/chats/claude-tasks/2026/10/log  - 2026-11-02 [[/notes/ideas]] filed\n"


def test_a_sidecar_newer_than_this_release_is_refused(tmp_path):
    """Its fields are unknown here, so rewriting it could lose them."""
    target = tmp_path / sidecar_path(NODE)
    target.parent.mkdir(parents=True)
    target.write_text(f"---\nmarginalia: {MARGINALIA_VERSION + 1}\ntags:\n- tea\n---\n")

    with pytest.raises(ValueError, match="newer"):
        read_sidecar(tmp_path, NODE)
