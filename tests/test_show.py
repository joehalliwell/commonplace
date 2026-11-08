"""Tests for `show`: everything known about one note, gathered from what already records it."""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
import yaml

from commonplace._annotate import link, tag
from commonplace._marginalia import read_marginalia, write_marginalia
from commonplace._search import _commands
from commonplace._show import render, show
from tests.porcelain import git

IDEAS = "---\ntitle: Ideas\ntype: Note\ntags: [drink]\n---\n\n# Ideas\n\nA tea house by the river.\n"


@pytest.fixture
def notes(test_repo, make_note):
    """A note with a title, type and tags of its own, and two others to link with."""
    test_repo.put(make_note(path="notes/ideas.md", content="# placeholder\n"))
    (test_repo.root / "notes/ideas.md").write_text(IDEAS)
    for path in ("journal/2026-11-01.md", "journal/2026-11-02.md"):
        test_repo.put(make_note(path=path, content="# Day\n\nThought about [[ideas]].\n"))
    test_repo.commit("Add notes")
    return test_repo


@pytest.fixture
def as_joe(monkeypatch):
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Joe")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "joe@example.com")


def test_show_gathers_what_frontmatter_and_marginalia_say(notes, as_joe):
    tag(notes, "ideas", ["revisit"])
    link(notes, "ideas", "2026-11-01", "where it started", on=date(2026, 11, 2))
    marginalia = read_marginalia(notes.root, Path("notes/ideas.md"))
    write_marginalia(notes, replace(marginalia, body=marginalia.body + "- 2026-11-02 half wrong\n"))

    shown = show(notes, "ideas")

    assert (shown["note"], shown["title"], shown["type"]) == ("/notes/ideas", "Ideas", "Note")
    assert shown["tags"] == {"own": ["drink"], "marginalia": ["revisit"]}
    assert {(n["direction"], n["other"]) for n in shown["links"]} == {
        ("out", "/journal/2026-11-01"),
        ("in", "/journal/2026-11-01"),
        ("in", "/journal/2026-11-02"),
    }
    # Lines that link are in links already; commentary is the rest of the log.
    assert shown["commentary"] == ["- 2026-11-02 half wrong"]
    assert shown["hidden"] is False


def test_show_index_says_whether_the_current_version_is_indexed(notes):
    assert show(notes, "ideas")["index"]["state"] == "not indexed"

    _commands.index(notes)
    indexed = show(notes, "ideas")["index"]
    assert indexed["state"] == "current"
    assert indexed["chunks"] > 0

    (notes.root / "notes/ideas.md").write_text(IDEAS + "\nMore.\n")
    git(notes.root, "commit", "-qam", "Edit")
    assert show(notes, "ideas")["index"]["state"] == "stale"


def test_show_index_is_current_while_an_uncommitted_edit_waits_for_its_commit(notes, make_note):
    """The index holds committed versions only, so current means the note's last commit is indexed."""
    notes.put(make_note(path="notes/other.md", content="# Other\n"))
    notes.commit("Move HEAD past the note")
    _commands.index(notes)

    (notes.root / "notes/ideas.md").write_text(IDEAS + "\nMore.\n")

    assert show(notes, "ideas")["index"]["state"] == "current"


def test_show_a_hidden_note_when_asked_by_name_and_says_so(notes, as_joe):
    """Asking for it by name is asking for it; hidden only keeps it out of what's offered."""
    tag(notes, "ideas", ["hidden"])

    assert show(notes, "ideas")["hidden"] is True


def test_render_is_the_record_as_yaml_keeping_the_header_and_the_sections_asked_for(notes, as_joe):
    tag(notes, "ideas", ["revisit"])
    shown = show(notes, "ideas")

    rendered = yaml.safe_load(render(shown, only=["tags"]))

    assert rendered["note"] == "/notes/ideas"
    assert rendered["tags"] == {"own": ["drink"], "marginalia": ["revisit"]}
    assert "links" not in rendered and "index" not in rendered
    assert yaml.safe_load(render(shown)) == shown


def test_show_cli_lists_each_link_with_its_direction(notes, as_joe, test_app, capsys):
    link(notes, "ideas", "2026-11-01", "and on", on=date(2026, 11, 2))
    capsys.readouterr()

    assert test_app(["show", "ideas", "--only", "links"]) == 0

    found = yaml.safe_load(capsys.readouterr().out)["links"]
    assert {
        "direction": "out",
        "other": "/journal/2026-11-01",
        "context": "- 2026-11-02 [[/journal/2026-11-01]] and on",
    } in found
    assert {"direction": "in", "other": "/journal/2026-11-02", "context": "Thought about [[ideas]]."} in found


def test_resolve_cli_prints_the_notes_absolute_path(notes, test_app, capsys):
    """So it composes: $EDITOR $(commonplace resolve ideas)."""
    assert test_app(["resolve", "ideas"]) == 0

    assert capsys.readouterr().out == f"{notes.root / 'notes/ideas.md'}\n"


def test_resolve_cli_prints_a_line_per_match_of_a_glob(notes, test_app, capsys):
    assert test_app(["resolve", "/journal/*"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        str(notes.root / "journal/2026-11-01.md"),
        str(notes.root / "journal/2026-11-02.md"),
    ]


def test_resolve_cli_an_ambiguous_name_fails_listing_candidates(notes, make_note, test_app, caplog):
    notes.put(make_note(path="notes/2026-11-01.md", content="# Also a day\n"))
    notes.commit("Add")

    with pytest.raises(SystemExit):
        test_app(["resolve", "2026-11-01"])

    assert "/journal/2026-11-01" in caplog.text
    assert "/notes/2026-11-01" in caplog.text


def test_show_cli_json_is_the_whole_record_for_skills(notes, test_app, capsys):
    assert test_app(["show", "ideas", "--json"]) == 0

    shown = json.loads(capsys.readouterr().out)
    assert set(shown) >= {"note", "title", "tags", "links", "commentary", "index", "hidden"}
