"""Tests for `journal`: creating and editing daily journal entries."""

import datetime as dt
import subprocess
from pathlib import Path

import pytest

from commonplace._journal import journal
from tests.porcelain import git


def test_journal_creates_and_commits_new_entry_for_given_date(test_repo, monkeypatch):
    seen: list[str] = []

    def fake_edit(content: str, editor: str) -> str:
        seen.append(content)
        return content + "Walked by the river.\n"

    monkeypatch.setattr("commonplace._journal.edit_in_editor", fake_edit)

    path = journal(test_repo, "2026-11-01")

    assert path == Path("journal/2026/11/2026-11-01.md")
    assert seen == ["# Sunday, November 01, 2026\n\n## Tasks\n\n## Notes\n\n"]
    assert "Walked by the river." in (test_repo.root / path).read_text()
    assert git(test_repo.root, "log", "-1", "--format=%s").strip() == "Update journal entry for 2026-11-01"


def test_journal_edits_existing_entry_preserving_frontmatter(test_repo, make_note, monkeypatch):
    path = Path("journal/2026/11/2026-11-01.md")
    test_repo.put(make_note(path=path, content="# Sunday\n\nFirst line.\n", metadata={"tags": ["day"]}))
    test_repo.commit("Seed entry")

    monkeypatch.setattr("commonplace._journal.edit_in_editor", lambda text, _: text + "Second line.\n")

    assert journal(test_repo, "2026-11-01") == path
    note = test_repo.get(path)
    assert note.metadata == {"tags": ["day"]}
    assert "First line.\nSecond line." in note.body


def test_journal_unchanged_edit_writes_nothing_and_commits_nothing(test_repo, monkeypatch):
    before = test_repo.head()
    monkeypatch.setattr("commonplace._journal.edit_in_editor", lambda *_: None)

    assert journal(test_repo, "2026-11-01") is None
    assert test_repo.head() == before
    assert not (test_repo.root / "journal/2026/11/2026-11-01.md").exists()


def test_journal_default_date_uses_local_today(test_repo, monkeypatch):
    today = dt.datetime.now()  # noqa: DTZ005
    monkeypatch.setattr("commonplace._journal.edit_in_editor", lambda text, _: text + "Today.\n")

    path = journal(test_repo)

    assert path == Path("journal") / today.strftime("%Y/%m/%Y-%m-%d.md")


def test_journal_invalid_date_raises_and_cli_exits(test_repo, test_app):
    with pytest.raises(ValueError, match="Invalid date format 'not-a-date'"):
        journal(test_repo, "not-a-date")

    with pytest.raises(SystemExit):
        test_app(["journal", "not-a-date"])


def test_journal_editor_errors_surface_as_value_error(test_repo, monkeypatch):
    def missing(*_):
        raise FileNotFoundError("no editor")

    monkeypatch.setattr("commonplace._journal.edit_in_editor", missing)
    with pytest.raises(ValueError, match="not found"):
        journal(test_repo, "2026-11-01")

    def failed(*_):
        raise subprocess.CalledProcessError(2, "vim")

    monkeypatch.setattr("commonplace._journal.edit_in_editor", failed)
    with pytest.raises(ValueError, match="exited with error code 2"):
        journal(test_repo, "2026-11-01")
