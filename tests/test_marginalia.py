"""Tests for marginalia: what's been said about a note since, kept in a shadow tree beside it."""

import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from commonplace._annotate import link, tag, unlink, untag
from commonplace._links import Target, UnresolvedNote
from commonplace._marginalia import (
    MARGINALIA_VERSION,
    Marginalia,
    marginalia_path,
    read_marginalia,
    write_marginalia,
)
from commonplace._show import links
from commonplace._types import Note
from commonplace._utils import load_frontmatter
from tests.porcelain import git

EXAMPLES = Path(__file__).parent / "resources" / "marginalia"
NOTE = Path("notes/ideas.md")


@pytest.fixture
def notes(test_repo, make_note):
    """A repo with a few committed notes."""
    for path in ("notes/ideas.md", "chats/claude-tasks/2026/10/log.md", "chats/claude-tasks/2026/11/log.md"):
        test_repo.put(make_note(path=path, content=f"# {path}\n\nSome text.\n"))
    test_repo.commit("Add notes")
    return test_repo


@pytest.fixture
def as_joe(monkeypatch):
    """Joe's identity, as git would find it in his config."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Joe")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "joe@example.com")


@pytest.fixture(params=range(1, MARGINALIA_VERSION + 1), ids=lambda v: f"marginalia-v{v}")
def any_marginalia_version(request, tmp_path) -> Path:
    """A repo root holding one example of marginalia per format version, all for `NOTE` with the same content."""
    source = EXAMPLES / f"v{request.param}.md"
    if not source.exists():
        pytest.fail(f"marginalia v{request.param} has no example at {source} — add one with the version bump")
    target = tmp_path / marginalia_path(NOTE)
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    return tmp_path


def test_every_marginalia_version_reads_to_the_same_marginalia(any_marginalia_version):
    marginalia = read_marginalia(any_marginalia_version, NOTE)

    assert marginalia.tags == ["hidden", "tea"]
    assert "[[/notes/todo]]" in marginalia.body


def test_a_note_without_marginalia_reads_as_untagged(tmp_path):
    assert read_marginalia(tmp_path, NOTE) == Marginalia(note=NOTE)


def test_marginalia_live_at_the_notes_path_in_the_shadow_tree():
    assert marginalia_path(Path("chats/claude/2026/06/tea.md")) == Path(
        ".commonplace/marginalia/chats/claude/2026/06/tea.md"
    )


def test_tags_round_trip_through_the_shadow_tree(test_repo):
    write_marginalia(test_repo, Marginalia(note=NOTE).tagged("hidden", "tea"))

    assert read_marginalia(test_repo.root, NOTE).tags == ["hidden", "tea"]
    metadata, _ = load_frontmatter((test_repo.root / marginalia_path(NOTE)).read_text())
    assert metadata["marginalia"] == MARGINALIA_VERSION


def test_tagging_again_with_a_tag_it_has_adds_nothing():
    assert Marginalia(note=NOTE).tagged("tea").tagged("tea", "hidden").tags == ["tea", "hidden"]


def test_untagging_leaves_the_body_alone():
    """The body is the log, appended to and never rewritten by tag changes."""
    marginalia = Marginalia(note=NOTE, tags=["tea", "hidden"], body="- 2026-11-01 filed as [[/notes/todo]]\n")

    assert marginalia.untagged("hidden") == Marginalia(note=NOTE, tags=["tea"], body=marginalia.body)


def test_tag_records_only_the_tags_in_the_frontmatter(notes, as_joe):
    """Where a moved note went is git's to say, so the marginalia record no commit."""
    tag(notes, "ideas", ["hidden", "tea"])

    metadata, _ = load_frontmatter((notes.root / marginalia_path(NOTE)).read_text())
    assert metadata == {"marginalia": MARGINALIA_VERSION, "tags": ["hidden", "tea"]}


def test_tag_commits_as_the_person_not_the_bot(notes, as_joe):
    """Tools tell a person's tags from their own by the commit's author, so they never remove them."""
    tag(notes, "ideas", ["hidden"])

    assert git(notes.root, "log", "-1", "--format=%an") == "Joe\n"


def test_tag_a_glob_tags_every_match(notes, as_joe):
    tag(notes, "/chats/claude-tasks/**", ["scheduled"])

    for month in ("10", "11"):
        assert read_marginalia(notes.root, Path(f"chats/claude-tasks/2026/{month}/log.md")).tags == ["scheduled"]


def test_untag_removes_only_the_tags_named(notes, as_joe):
    tag(notes, "ideas", ["hidden", "tea"])

    untag(notes, "ideas", ["hidden"])

    assert read_marginalia(notes.root, NOTE).tags == ["tea"]


def test_tag_a_span_is_refused(notes, as_joe):
    """Tags describe whole notes; only links reach inside one."""
    with pytest.raises(UnresolvedNote, match="whole notes"):
        tag(notes, "ideas#Tea house", ["hidden"])


def test_every_wikilink_in_marginalia_is_a_link_from_its_note(any_marginalia_version):
    """Free prose links count too: 'filed as [[/notes/todo]]' says something about this note."""
    assert _targets(any_marginalia_version) == ["/notes/todo"]


def test_link_to_an_ambiguous_name_fails_and_writes_nothing(notes, as_joe):
    with pytest.raises(UnresolvedNote):  # Two notes are called log
        link(notes, "ideas", "log", "")

    assert read_marginalia(notes.root, NOTE) == Marginalia(note=NOTE)


def test_link_records_the_edge_and_commits_as_the_person(notes, as_joe):
    link(notes, "ideas", '2026/10/log#"Some text."', "the same thought, scheduled", on=date(2026, 11, 2))

    marginalia = read_marginalia(notes.root, NOTE)
    assert marginalia.body.splitlines() == [
        '- 2026-11-02 [[/chats/claude-tasks/2026/10/log#"Some text."]] the same thought, scheduled'
    ]
    assert _targets(notes.root) == ['/chats/claude-tasks/2026/10/log#"Some text."']
    assert git(notes.root, "log", "-1", "--format=%an") == "Joe\n"


def test_link_keeps_the_tags_and_appends_after_whats_there(notes, as_joe):
    tag(notes, "ideas", ["tea"])
    link(notes, "ideas", "2026/10/log", "", on=date(2026, 11, 2))
    link(notes, "ideas", "2026/11/log", "and again", on=date(2026, 11, 3))

    marginalia = read_marginalia(notes.root, NOTE)
    assert marginalia.tags == ["tea"]
    assert _targets(notes.root) == ["/chats/claude-tasks/2026/10/log", "/chats/claude-tasks/2026/11/log"]


def test_link_from_a_span_is_refused(notes, as_joe):
    """Marginalia speak for a whole note; the span belongs at the other end."""
    with pytest.raises(UnresolvedNote, match="whole notes"):
        link(notes, "ideas#Something", "2026/10/log", "")


def test_unlink_removes_only_the_edges_to_that_target(notes, as_joe):
    link(notes, "ideas", "2026/10/log", "", on=date(2026, 11, 2))
    link(notes, "ideas", "2026/11/log", "", on=date(2026, 11, 2))

    assert unlink(notes, "ideas", "2026/10/log") == 1

    assert _targets(notes.root) == ["/chats/claude-tasks/2026/11/log"]


def test_unlink_an_edge_that_isnt_there_fails(notes, as_joe):
    with pytest.raises(ValueError, match="no link"):
        unlink(notes, "ideas", "2026/10/log")


def test_unlink_a_link_whose_target_is_gone_by_writing_it_as_the_marginalia_do(notes, as_joe):
    """doctor reports dead links; they must stay removable once their note can no longer be named."""
    link(notes, "ideas", "2026/10/log", "", on=date(2026, 11, 2))
    notes.remove(Path("chats/claude-tasks/2026/10/log.md"))
    notes.commit("Delete")

    with pytest.raises(UnresolvedNote, match="/chats/claude-tasks/2026/10/log"):  # The hint shows how
        unlink(notes, "ideas", "2026/10/log")
    assert unlink(notes, "ideas", "[[/chats/claude-tasks/2026/10/log]]") == 1

    assert _targets(notes.root) == []


def test_link_cli_takes_the_rest_of_the_line_as_why(notes, as_joe, test_app):
    assert test_app(["link", "ideas", "2026/10/log", "filed", "as", "an", "idea"]) == 0

    [line] = read_marginalia(notes.root, NOTE).body.splitlines()
    assert line.endswith("[[/chats/claude-tasks/2026/10/log]] filed as an idea")


def _targets(root: Path) -> list[str]:
    return [edge.link.target for edge in _note(root).said]


def _note(root: Path) -> Note:
    return Note(NOTE, "", marginalia=read_marginalia(root, NOTE))


def _found(neighbours, direction: str) -> set[tuple[str, str, str]]:
    return {(n.direction, n.other, n.context) for n in neighbours if n.direction == direction}


def test_links_incoming_gathers_marginalia_edges_and_links_in_notes(notes, as_joe, make_note):
    notes.put(make_note(path="journal/2026-11-02.md", content="# Day\n\nAdded to [[ideas]].\n"))
    notes.commit("Journal")
    link(notes, "2026/10/log", 'ideas#"Some text."', "the same thought", on=date(2026, 11, 2))

    assert _found(links(notes, NOTE), "in") == {
        ("in", "/chats/claude-tasks/2026/10/log", '- 2026-11-02 [[/notes/ideas#"Some text."]] the same thought'),
        ("in", "/journal/2026-11-02", "Added to [[ideas]]."),
    }


def test_links_outgoing_gathers_marginalia_edges_and_links_in_the_notes_own_text(notes, as_joe, make_note):
    """For a foreign note, marginalia are its only outgoing links; for your own, both count."""
    notes.put(make_note(path="notes/ideas.md", content="# Ideas\n\nSee [[2026/11/log]].\n"))
    notes.commit("Edit")
    link(notes, "ideas", "2026/10/log", "scheduled", on=date(2026, 11, 2))

    assert _found(links(notes, NOTE), "out") == {
        ("out", "/chats/claude-tasks/2026/10/log", "- 2026-11-02 [[/chats/claude-tasks/2026/10/log]] scheduled"),
        ("out", "/chats/claude-tasks/2026/11/log", "See [[2026/11/log]]."),
    }


def test_into_finds_every_kind_of_link_to_the_note_in_text_and_marginalia(test_repo):
    files = {
        "notes/ideas.md": "# Ideas\n",
        "notes/other.md": "# Other\n",
        "journal/a.md": "See [[ideas]].\n",
        "journal/b.md": "See [[/notes/ideas#Tea house]].\n",
        "journal/c.md": "See [the list](../notes/ideas.md).\n",
        "journal/d.md": "See [[other]] and [elsewhere](../notes/other.md).\n",
        "journal/e.md": "See [the list](../notes/ide%61s.md).\n",
        "chats/claude/x.md": "Quoted: [[ideas]].\n",
        str(marginalia_path(Path("notes/other.md"))): "---\nmarginalia: 1\n---\n\n- 2026-11-02 [[/notes/ideas]] why\n",
    }
    for path, text in files.items():
        (test_repo.root / path).parent.mkdir(parents=True, exist_ok=True)
        (test_repo.root / path).write_text(text)

    found = test_repo.into(Path("notes/ideas.md"))

    # Chats quote links rather than make them, as for the link check.
    assert [(str(Target(edge.node)), source.line(edge)) for source, edge in found] == [
        ("/journal/a", "See [[ideas]]."),
        ("/journal/b", "See [[/notes/ideas#Tea house]]."),
        ("/journal/c", "See [the list](../notes/ideas.md)."),
        ("/journal/e", "See [the list](../notes/ide%61s.md)."),
        ("/notes/other", "- 2026-11-02 [[/notes/ideas]] why"),
    ]


def test_a_wikilink_quoted_as_code_in_marginalia_is_commentary_not_a_link(notes):
    """Marginalia are markdown, read as the link check reads any note."""
    write_marginalia(
        notes, Marginalia(note=NOTE, body="- write one as `[[/notes/todo]]`\n- 2026-11-02 [[/notes/done]]\n")
    )

    assert _targets(notes.root) == ["/notes/done"]
    assert _note(notes.root).commentary == ["- write one as `[[/notes/todo]]`"]


def test_unlink_leaves_a_line_that_only_quotes_the_link(notes, as_joe):
    link(notes, "ideas", "2026/10/log", "", on=date(2026, 11, 2))
    marginalia = read_marginalia(notes.root, NOTE)
    quoted = "- unlink with `[[/chats/claude-tasks/2026/10/log]]`\n"
    write_marginalia(notes, replace(marginalia, body=marginalia.body + quoted))

    assert unlink(notes, "ideas", "2026/10/log") == 1

    assert read_marginalia(notes.root, NOTE).body == quoted


def test_a_path_link_in_marginalia_lands_as_if_written_in_the_note(notes, as_joe):
    """A note and its marginalia are one document, so a relative path is measured from the note."""
    line = "- see [the log](../chats/claude-tasks/2026/10/log.md)"
    write_marginalia(notes, Marginalia(note=NOTE, body=f"{line}\n"))

    assert _found(links(notes, NOTE), "out") == {("out", "/chats/claude-tasks/2026/10/log", line)}


def test_links_leave_out_hidden_notes_at_the_other_end_unless_asked(notes, as_joe):
    link(notes, "2026/10/log", "ideas", "", on=date(2026, 11, 2))
    link(notes, "ideas", "2026/11/log", "", on=date(2026, 11, 2))
    tag(notes, "/chats/claude-tasks/**", ["hidden"])

    assert links(notes, NOTE) == []
    assert len(links(notes, NOTE, include_hidden=True)) == 2


def test_add_link_to_a_tag_labels_the_note(notes):
    notes.add_link(NOTE, "tag:tea")

    assert read_marginalia(notes.root, NOTE).tags == ["tea"]
    assert read_marginalia(notes.root, NOTE).body == ""


def test_add_link_to_a_name_with_no_note_is_an_edge_all_the_same(notes):
    """An edge needs no file at its other end: 'alice' is a node whether or not she has a note."""
    notes.add_link(NOTE, "alice", "met at the conference", on=date(2026, 11, 2))

    assert _targets(notes.root) == ["alice"]


def test_add_link_writes_for_the_next_commit_without_committing(notes):
    head = git(notes.root, "rev-parse", "HEAD")

    notes.add_link(NOTE, "tag:tea")

    assert git(notes.root, "rev-parse", "HEAD") == head
    notes.commit("Tag")
    assert git(notes.root, "rev-parse", "HEAD") != head


@pytest.mark.parametrize("note", [Path("../config.toml"), Path("/etc/passwd")])
def test_add_link_from_a_note_outside_the_repository_is_refused(notes, note):
    """Marginalia sit at their note's path under the shadow tree, so `../config.toml` would be the config."""
    config = (notes.root / ".commonplace" / "config.toml").read_text()

    with pytest.raises(ValueError):
        notes.add_link(note, "tag:tea")

    assert (notes.root / ".commonplace" / "config.toml").read_text() == config


def test_remove_link_says_how_many_edges_went_and_a_tag_counts_once(notes):
    notes.add_link(NOTE, "alice", on=date(2026, 11, 2))
    notes.add_link(NOTE, "alice", "again", on=date(2026, 11, 3))
    notes.add_link(NOTE, "tag:tea")

    assert notes.remove_link(NOTE, "alice") == 2
    assert notes.remove_link(NOTE, "tag:tea") == 1
    assert notes.remove_link(NOTE, "tag:tea") == 0
    assert read_marginalia(notes.root, NOTE) == Marginalia(note=NOTE)


def test_marginalia_newer_than_this_release_are_refused(tmp_path):
    """Its fields are unknown here, so rewriting it could lose them."""
    target = tmp_path / marginalia_path(NOTE)
    target.parent.mkdir(parents=True)
    target.write_text(f"---\nmarginalia: {MARGINALIA_VERSION + 1}\ntags:\n- tea\n---\n")

    with pytest.raises(ValueError, match="newer"):
        read_marginalia(tmp_path, NOTE)
