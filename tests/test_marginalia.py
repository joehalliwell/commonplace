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
from commonplace._types import Note, TagFilter
from commonplace._utils import load_frontmatter
from tests.porcelain import git

EXAMPLES = Path(__file__).parent / "resources" / "marginalia"
NOTE = Path("notes/ideas.md")
LOG = Target(Path("chats/claude-tasks/2026/10/log.md"))


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


def test_tag_keeps_an_uncommitted_edit_to_the_marginalia(notes, as_joe):
    tag(notes, "ideas", ["tea"])
    file = notes.root / marginalia_path(NOTE)
    file.write_text(file.read_text() + "\n- 2026-11-15 my own aside\n")

    tag(notes, "ideas", ["hidden"])

    metadata, body = load_frontmatter(file.read_text())
    assert (metadata["tags"], "my own aside" in body) == (["tea", "hidden"], True)


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


@pytest.mark.parametrize(("source", "target"), [("ideas", "nobody"), ("nobody", "ideas")], ids=["to", "from"])
def test_link_cli_between_a_note_and_a_name_with_no_note_fails_and_writes_nothing(
    notes, as_joe, test_app, source, target
):
    """The CLI joins notes that exist; an edge to a name with no note is for writers that mean one."""
    with pytest.raises(SystemExit):
        test_app(["link", source, target, "why"])

    assert read_marginalia(notes.root, NOTE) == Marginalia(note=NOTE)


def test_link_to_an_ambiguous_name_fails_and_writes_nothing(notes, as_joe):
    with pytest.raises(UnresolvedNote):  # Two notes are called log
        link(notes, "ideas", "log", "")

    assert read_marginalia(notes.root, NOTE) == Marginalia(note=NOTE)


def test_link_records_the_edge_and_commits_as_the_person(notes, as_joe):
    link(notes, "ideas", '2026/10/log#"Some text."', "the same thought, scheduled", on=date(2026, 11, 2))

    marginalia = read_marginalia(notes.root, NOTE)
    assert marginalia.body.splitlines() == [
        '- 2026-11-02 [the same thought, scheduled](</chats/claude-tasks/2026/10/log.md#"Some text.">)'
    ]
    assert _targets(notes.root) == ['/chats/claude-tasks/2026/10/log.md#"Some text."']
    assert git(notes.root, "log", "-1", "--format=%an") == "Joe\n"


def test_link_keeps_the_tags_and_appends_after_whats_there(notes, as_joe):
    tag(notes, "ideas", ["tea"])
    link(notes, "ideas", "2026/10/log", "", on=date(2026, 11, 2))
    link(notes, "ideas", "2026/11/log", "and again", on=date(2026, 11, 3))

    marginalia = read_marginalia(notes.root, NOTE)
    assert marginalia.tags == ["tea"]
    assert _targets(notes.root) == ["/chats/claude-tasks/2026/10/log.md", "/chats/claude-tasks/2026/11/log.md"]


def test_link_from_a_span_is_refused(notes, as_joe):
    """Marginalia speak for a whole note; the span belongs at the other end."""
    with pytest.raises(UnresolvedNote, match="whole notes"):
        link(notes, "ideas#Something", "2026/10/log", "")


def test_unlink_removes_only_the_edges_to_that_target(notes, as_joe):
    link(notes, "ideas", "2026/10/log", "", on=date(2026, 11, 2))
    link(notes, "ideas", "2026/11/log", "", on=date(2026, 11, 2))

    assert unlink(notes, "ideas", "2026/10/log") == 1

    assert _targets(notes.root) == ["/chats/claude-tasks/2026/11/log.md"]


def test_unlink_removes_a_wikilink_written_before_links_were_written_as_paths(notes, as_joe):
    write_marginalia(notes, Marginalia(note=NOTE, body="- 2026-11-01 [[/chats/claude-tasks/2026/10/log]] by hand\n"))

    assert unlink(notes, "ideas", "2026/10/log") == 1

    assert _targets(notes.root) == []


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
    assert unlink(notes, "ideas", "/chats/claude-tasks/2026/10/log.md") == 1

    assert _targets(notes.root) == []


def test_link_cli_takes_the_rest_of_the_line_as_why(notes, as_joe, test_app):
    assert test_app(["link", "ideas", "2026/10/log", "filed", "as", "an", "idea"]) == 0

    [line] = read_marginalia(notes.root, NOTE).body.splitlines()
    assert line.endswith("[filed as an idea](/chats/claude-tasks/2026/10/log.md)")


def _targets(root: Path) -> list[str]:
    return [edge.link.target for edge in _note(root).said]


def _note(root: Path) -> Note:
    return Note(NOTE, "", marginalia=read_marginalia(root, NOTE))


def _found(neighbours, direction: str) -> set[tuple]:
    return {(n.direction, n.other, n.text) for n in neighbours if n.direction == direction}


def test_links_incoming_gathers_marginalia_edges_and_links_in_notes(notes, as_joe, make_note):
    notes.put(make_note(path="journal/2026-11-02.md", content="# Day\n\nAdded to [[ideas]].\n"))
    notes.commit("Journal")
    link(notes, "2026/10/log", 'ideas#"Some text."', "the same thought", on=date(2026, 11, 2))

    assert _found(links(notes, NOTE), "in") == {
        ("in", "/chats/claude-tasks/2026/10/log", "the same thought"),
        ("in", "/journal/2026-11-02", ""),
    }


def test_links_outgoing_gathers_marginalia_edges_and_links_in_the_notes_own_text(notes, as_joe, make_note):
    """For a foreign note, marginalia are its only outgoing links; for your own, both count."""
    notes.put(make_note(path="notes/ideas.md", content="# Ideas\n\nSee [[2026/11/log]].\n"))
    notes.commit("Edit")
    link(notes, "ideas", "2026/10/log", "scheduled", on=date(2026, 11, 2))

    assert _found(links(notes, NOTE), "out") == {
        ("out", "/chats/claude-tasks/2026/10/log", "scheduled"),
        ("out", "/chats/claude-tasks/2026/11/log", ""),
    }


@pytest.mark.parametrize(
    ("target", "why", "line"),
    [
        (Target(NOTE), "filed as tea", "- 2026-11-02 [filed as tea](/notes/ideas.md)"),
        (Target(NOTE), "", "- 2026-11-02 [/notes/ideas](/notes/ideas.md)"),
        (
            Target(NOTE, "Tea house"),
            "see [this] | that",
            "- 2026-11-02 [see \\[this\\] | that](</notes/ideas.md#Tea house>)",
        ),
    ],
    ids=["why", "no why", "span and a why with brackets"],
)
def test_linked_writes_a_markdown_link_to_the_resolved_path(target, why, line):
    """What the link says is the reason, or else the target's name; any reason, escaped, reads back as written."""
    linked = Marginalia(NOTE).linked(target, why, date(2026, 11, 2))

    assert linked.body == f"{line}\n"
    assert [(edge.link.target, edge.link.text) for edge in linked.written] == [(target.href, why or str(target))]


def test_marginalia_frontmatter_cites_as_a_notes_does(tmp_path):
    """No special case: a `source` key in marginalia is provenance, an edge from the note, as in the note itself."""
    text = "---\nmarginalia: 2\nsource: notes/ideas.md\n---\n\n- 2026-11-02 [[/notes/tea]]\n"
    (tmp_path / marginalia_path(NOTE)).parent.mkdir(parents=True)
    (tmp_path / marginalia_path(NOTE)).write_text(text)

    said = _note(tmp_path).said

    assert [(edge.link.target, edge.link.kind.value, edge.link.line) for edge in said] == [
        ("notes/ideas.md", "citation", 3),
        ("/notes/tea", "wikilink", 6),
    ]


def test_unlinking_a_frontmatter_citation_removes_nothing_and_says_so(tmp_path):
    """A citation is in the frontmatter, not on a line of the body, so there is no line of it to drop."""
    text = "---\nmarginalia: 2\nsource: notes/ideas.md\n---\n\n- 2026-11-02 [[/notes/tea]]\n"
    (tmp_path / marginalia_path(NOTE)).parent.mkdir(parents=True)
    (tmp_path / marginalia_path(NOTE)).write_text(text)
    note = _note(tmp_path)

    marginalia, removed = note.unlinked("notes/ideas.md")

    assert (removed, marginalia.body) == (0, note.marginalia.body)


def test_commentary_is_every_line_of_the_body_that_links_nowhere_whatever_the_frontmatter_cites():
    marginalia = Marginalia(NOTE, body="Plain words.\n- [[/notes/tea]]\n", properties={"source": "notes/ideas.md"})

    assert Note(NOTE, "", marginalia=marginalia).commentary == ["Plain words."]


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

    found = [edge for _, edge in test_repo.into(Path("notes/ideas.md"))]

    # Chats quote links rather than make them, as for the link check.
    assert [(str(Target(edge.node)), edge.link.text) for edge in found] == [
        ("/journal/a", ""),
        ("/journal/b", ""),
        ("/journal/c", "the list"),
        ("/journal/e", "the list"),
        ("/notes/other", ""),
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

    assert _found(links(notes, NOTE), "out") == {("out", "/chats/claude-tasks/2026/10/log", "the log")}


def test_links_leave_out_notes_at_the_other_end_the_tag_filter_excludes(notes, as_joe):
    link(notes, "2026/10/log", "ideas", "", on=date(2026, 11, 2))
    link(notes, "ideas", "2026/11/log", "", on=date(2026, 11, 2))
    tag(notes, "/chats/claude-tasks/**", ["scheduled"])

    assert links(notes, NOTE, TagFilter(without=frozenset({"scheduled"}))) == []
    assert len(links(notes, NOTE)) == 2


def test_label_and_unlabel_change_only_the_marginalias_tags(notes):
    notes.label(NOTE, "tea", "hidden")
    notes.unlabel(NOTE, "hidden")

    assert read_marginalia(notes.root, NOTE) == Marginalia(note=NOTE, tags=["tea"])


def test_add_link_writes_the_path_its_target_resolves_to(notes):
    """Ambiguous links are read; only resolved ones are written, so a later note of the same name changes nothing."""
    notes.add_link(NOTE, LOG, on=date(2026, 11, 2))

    body = "- 2026-11-02 [/chats/claude-tasks/2026/10/log](/chats/claude-tasks/2026/10/log.md)\n"
    assert read_marginalia(notes.root, NOTE) == Marginalia(note=NOTE, body=body)


@pytest.mark.parametrize(
    "write", [lambda repo, note: repo.add_link(note, LOG), lambda repo, note: repo.label(note, "tea")]
)
def test_marginalia_writes_hold_for_the_next_commit_without_committing(notes, write):
    head = git(notes.root, "rev-parse", "HEAD")

    write(notes, NOTE)

    assert git(notes.root, "rev-parse", "HEAD") == head
    notes.commit("Annotate")
    assert git(notes.root, "rev-parse", "HEAD") != head


@pytest.mark.parametrize(
    "write", [lambda repo, note: repo.add_link(note, LOG), lambda repo, note: repo.label(note, "tea")]
)
@pytest.mark.parametrize("note", [Path("../config.toml"), Path("/etc/passwd")])
def test_marginalia_writes_for_a_note_outside_the_repository_are_refused(notes, note, write):
    """Marginalia sit at their note's path under the shadow tree, so `../config.toml` would be the config."""
    config = (notes.root / ".commonplace" / "config.toml").read_text()

    with pytest.raises(ValueError):
        write(notes, note)

    assert (notes.root / ".commonplace" / "config.toml").read_text() == config


def test_remove_link_says_how_many_edges_went(notes):
    notes.add_link(NOTE, LOG, on=date(2026, 11, 2))
    notes.add_link(NOTE, LOG, "again", on=date(2026, 11, 3))

    assert notes.remove_link(NOTE, LOG) == 2
    assert notes.remove_link(NOTE, LOG) == 0
    assert read_marginalia(notes.root, NOTE) == Marginalia(note=NOTE)


def test_marginalia_keep_every_property_through_a_rewrite(notes):
    """Marginalia are the counterpart half of a node, so whatever a tool adds there must survive the next edit."""
    write_marginalia(notes, Marginalia(note=NOTE, properties={"status": "draft", "seen": [1, 2]}))

    notes.label(NOTE, "tea")

    marginalia = read_marginalia(notes.root, NOTE)
    assert (marginalia.tags, marginalia.properties) == (["tea"], {"status": "draft", "seen": [1, 2]})


def test_marginalia_v1s_ref_is_dropped_not_kept_as_a_property(any_marginalia_version, test_repo):
    """v2 dropped `ref`: git's rename history says where a moved note went."""
    assert read_marginalia(any_marginalia_version, NOTE).properties == {}


def test_marginalia_newer_than_this_release_are_refused(tmp_path):
    """Its fields are unknown here, so rewriting it could lose them."""
    target = tmp_path / marginalia_path(NOTE)
    target.parent.mkdir(parents=True)
    target.write_text(f"---\nmarginalia: {MARGINALIA_VERSION + 1}\ntags:\n- tea\n---\n")

    with pytest.raises(ValueError, match="newer"):
        read_marginalia(tmp_path, NOTE)
