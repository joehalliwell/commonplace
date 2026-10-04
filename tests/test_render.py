"""Tests for `doctor --render`: replaying stored archives, in capture order, into the chats they render."""

import json
from pathlib import Path

import pytest

from commonplace._doctor import doctor
from commonplace._import._render import RENDER_MESSAGE
from commonplace._utils import load_frontmatter
from tests.porcelain import git

NOTE = Path("chats/claude/2026/07/2026-07-15-hello.md")


@pytest.fixture
def store(test_repo, tmp_path, write_jsonl_gz):
    """Store, and commit, a Claude wire archive whose one conversation ends with `reply`."""

    def _store(reply: str, fetched_at: str | None = None) -> str:
        thread = {
            "uuid": "c1",
            "name": "Hello",
            "created_at": "2026-07-15T00:00:00Z",
            "chat_messages": [
                {"sender": "human", "text": "hello", "created_at": "2026-07-15T00:00:00Z"},
                {"sender": "assistant", "text": reply, "created_at": "2026-07-15T00:00:01Z"},
            ],
        }
        # v3 dates its capture; v2 doesn't, like the exports.
        header = (
            {"wire": "claude", "version": 3, "fetched_at": fetched_at}
            if fetched_at
            else {"wire": "claude", "version": 2}
        )
        entries = [
            {"endpoint": "conversations", "response": "[]"},
            {"endpoint": "conversation", "cid": "c1", "response": json.dumps(thread)},
        ]
        archive = tmp_path / reply
        archive.mkdir()
        blob = test_repo.store_blob(write_jsonl_gz(archive / "claude-wire.jsonl.gz", [header, *entries]))
        test_repo.commit(f"Store {reply}", auto_index=False)
        return blob.path.as_posix()

    return _store


def _render(repo, **kwargs):
    return doctor(repo, scaffold=False, links=False, render=True, **kwargs)


def _note(repo) -> tuple[dict, str]:
    return load_frontmatter((repo.root / NOTE).read_text())


def _head(repo) -> str:
    return git(repo.root, "log", "-1", "--format=%s").strip()


def test_render_writes_the_chats_a_stored_archive_holds_in_one_commit(test_repo, store):
    store("hi back", fetched_at="2026-08-01T00:00:00+00:00")

    _render(test_repo)

    assert "hi back" in _note(test_repo)[1]
    assert _head(test_repo) == RENDER_MESSAGE
    assert git(test_repo.root, "status", "--porcelain") == ""


def test_render_takes_the_newest_capture_whatever_order_archives_were_stored(test_repo, store):
    store("newer", fetched_at="2026-08-02T00:00:00+00:00")
    store("older", fetched_at="2026-08-01T00:00:00+00:00")

    _render(test_repo)

    assert "newer" in _note(test_repo)[1]


def test_render_lets_an_undated_archive_lose_to_a_dated_one(test_repo, store):
    store("dated", fetched_at="2026-08-01T00:00:00+00:00")
    store("undated")

    _render(test_repo)

    assert "dated" in _note(test_repo)[1]


@pytest.mark.parametrize("first, second", [("alpha", "omega"), ("omega", "alpha")])
def test_render_orders_undated_archives_by_when_they_were_stored(test_repo, store, first, second):
    store(first)
    store(second)

    _render(test_repo)

    assert second in _note(test_repo)[1]


def test_render_points_source_export_at_the_archive_that_won(test_repo, store):
    store("older", fetched_at="2026-08-01T00:00:00+00:00")
    newer = store("newer", fetched_at="2026-08-02T00:00:00+00:00")

    _render(test_repo)

    assert _note(test_repo)[0]["source_export"] == newer


def test_render_rewrites_a_note_its_last_import_wrote(test_repo, store):
    store("hi back", fetched_at="2026-08-01T00:00:00+00:00")
    _render(test_repo)
    (test_repo.root / NOTE).write_text((test_repo.root / NOTE).read_text().replace("hi back", "stale"))
    git(test_repo.root, "commit", "-qam", "Import from 'x' using 'claude' importer")

    _render(test_repo)

    assert "hi back" in _note(test_repo)[1]


def test_render_leaves_a_hand_edited_note_alone_and_names_it(test_repo, store):
    store("hi back", fetched_at="2026-08-01T00:00:00+00:00")
    _render(test_repo)
    edited = (test_repo.root / NOTE).read_text() + "\nMy own thought.\n"
    (test_repo.root / NOTE).write_text(edited)
    git(test_repo.root, "commit", "-qam", "Auto-commit before sync at 2026-10-04T00:00:00+00:00")
    store("newer", fetched_at="2026-08-02T00:00:00+00:00")

    report = _render(test_repo)

    assert (test_repo.root / NOTE).read_text() == edited
    assert any(NOTE.as_posix() in warning for warning in report.warnings)


def test_render_leaves_an_uncommitted_edit_alone(test_repo, store):
    store("hi back", fetched_at="2026-08-01T00:00:00+00:00")
    _render(test_repo)
    edited = (test_repo.root / NOTE).read_text() + "\nMy own thought.\n"
    (test_repo.root / NOTE).write_text(edited)
    store("newer", fetched_at="2026-08-02T00:00:00+00:00")

    _render(test_repo)

    assert (test_repo.root / NOTE).read_text() == edited


def test_render_check_reports_without_writing(test_repo, store):
    store("hi back", fetched_at="2026-08-01T00:00:00+00:00")
    head = git(test_repo.root, "rev-parse", "HEAD")

    report = _render(test_repo, check=True)

    assert report.actions
    assert not (test_repo.root / NOTE).exists()
    assert git(test_repo.root, "rev-parse", "HEAD") == head


def test_render_is_idempotent(test_repo, store):
    store("hi back", fetched_at="2026-08-01T00:00:00+00:00")
    _render(test_repo)
    head = git(test_repo.root, "rev-parse", "HEAD")

    report = _render(test_repo)

    assert report.actions == []
    assert git(test_repo.root, "rev-parse", "HEAD") == head


def test_render_counts_chats_no_stored_archive_renders(test_repo, store):
    store("hi back", fetched_at="2026-08-01T00:00:00+00:00")
    orphan = test_repo.root / "chats" / "claude" / "2025" / "01" / "2025-01-01-gone.md"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("---\ntype: Chat\n---\n# Gone\n")
    git(test_repo.root, "add", ".")
    git(test_repo.root, "commit", "-qm", "Import from 'old' using 'claude' importer")

    report = _render(test_repo)

    assert orphan.exists()
    assert any("1 chat" in warning for warning in report.warnings)


def test_render_is_off_by_default(test_repo, store):
    store("hi back", fetched_at="2026-08-01T00:00:00+00:00")

    doctor(test_repo)

    assert not (test_repo.root / NOTE).exists()


def test_doctor_cli_render_flag_renders(test_app, test_repo, store):
    store("hi back", fetched_at="2026-08-01T00:00:00+00:00")

    assert test_app(["doctor", "--render", "--no-links"]) == 0

    assert (test_repo.root / NOTE).exists()
