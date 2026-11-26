import json
import os
from datetime import UTC, datetime
from pathlib import Path

from commonplace._fetch._antigravity import AntigravityFetcher
from commonplace._fetch._commands import fetch
from commonplace._progress import on, rows
from commonplace._wire import archive_names, entry_body, read_entries, read_header
from tests.fetching import fetching, owned
from tests.porcelain import git

OLD = datetime(2026, 9, 1, tzinfo=UTC)
NEW = datetime(2026, 10, 1, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n\x00\xff"


def _transcript(prompt: str, reply: str, timestamp: str) -> str:
    lines = [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": timestamp,
            "content": f"<USER_REQUEST>\n{prompt}\n</USER_REQUEST>",
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": timestamp,
            "model": "gemini-4-neon-high",
            "content": reply,
        },
    ]
    return "".join(json.dumps(line) + "\n" for line in lines)


def _write(path: Path, content: str | bytes, modified: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    os.utime(path, (modified.timestamp(), modified.timestamp()))
    return path


#: Every file a capture of `_antigravity_home` since the epoch records, in order.
EVERYTHING = [
    "conv-new/.system_generated/logs/transcript.jsonl",
    "conv-new/.system_generated/logs/transcript_full.jsonl",
    "conv-new/.system_generated/steps/1/output.txt",
    "conv-new/.user_uploaded/shot.png",
    "conv-new/plan.md",
    "conv-new/scratch/notes.txt",
    "conv-old/.system_generated/logs/transcript_full.jsonl",
]


def _antigravity_home(tmp_path: Path) -> Path:
    """An Antigravity home with an old conversation, a new one with artefacts/uploads, and a dir with no transcript."""
    home = tmp_path / ".gemini" / "antigravity-cli"
    brain = home / "brain"
    _write(
        brain / "conv-old" / ".system_generated" / "logs" / "transcript_full.jsonl",
        _transcript("old work", "Done.", "2026-09-01T10:00:00Z"),
        OLD,
    )
    _write(
        brain / "conv-new" / ".system_generated" / "logs" / "transcript_full.jsonl",
        _transcript("new work", "On it.", "2026-10-01T10:00:00Z"),
        NEW,
    )
    _write(
        brain / "conv-new" / ".system_generated" / "logs" / "transcript.jsonl",
        _transcript("new work", "On it.", "2026-10-01T10:00:00Z"),
        NEW,
    )
    _write(brain / "conv-new" / ".system_generated" / "steps" / "1" / "output.txt", "line one\r\nline two", NEW)
    _write(brain / "conv-new" / ".user_uploaded" / "shot.png", PNG, NEW)
    _write(brain / "conv-new" / "plan.md", "# Plan\n", NEW)
    _write(brain / "conv-new" / "scratch" / "notes.txt", "scratch\n", NEW)
    # A directory with artefacts only and no JSONL transcript (e.g. an IDE-only session) is skipped.
    _write(brain / "ide-only" / "task.md", "# Task\n", NEW)
    return home


def test_fetch_antigravity_records_each_conversation_whole_byte_for_byte(tmp_path):
    """Capture is total and dumb: artefacts, uploads and step outputs stay verbatim in the archive."""
    home = _antigravity_home(tmp_path)

    captured = owned(AntigravityFetcher, root=home).fetch(tmp_path, since=None)

    entries = _entries(captured)
    assert sorted((e["endpoint"], e["path"]) for e in entries) == [("file", path) for path in sorted(EVERYTHING)]
    assert all(entry_body(e) == (home / "brain" / e["path"]).read_bytes() for e in entries)


def test_fetch_antigravity_counts_every_file_it_records_on_the_sources_row(tmp_path):
    fetcher = owned(AntigravityFetcher, root=_antigravity_home(tmp_path))

    with rows(["antigravity"]) as table, on(table["antigravity"]):
        captured = fetcher.fetch(tmp_path, since=NEW - (NEW - OLD) / 2)

        assert table["antigravity"].done()[0] == len(_entries(captured))


def test_fetch_antigravity_writes_one_archive_per_conversation(tmp_path):
    captured = owned(AntigravityFetcher, root=_antigravity_home(tmp_path)).fetch(tmp_path, since=None)

    archives = {a.parent.relative_to(tmp_path).as_posix(): a for a in captured}
    assert sorted(archives) == ["conv-new", "conv-old"]
    assert all(read_header(a).source == "antigravity" for a in archives.values())
    assert sorted(e["path"] for e in read_entries(archives["conv-new"])) == sorted(EVERYTHING[:-1])


def test_fetch_antigravity_incremental_reads_conversations_changed_after_the_cursor(tmp_path):
    captured = owned(AntigravityFetcher, root=_antigravity_home(tmp_path)).fetch(
        tmp_path, since=datetime(2026, 9, 15, tzinfo=UTC)
    )

    assert _paths(captured) == sorted(EVERYTHING[:-1])


def test_fetch_antigravity_conversation_whose_artefact_changed_is_read_again(tmp_path):
    """An artefact or step output can be written after the transcript last changed."""
    home = _antigravity_home(tmp_path)
    _write(home / "brain" / "conv-old" / "report.md", "# Report\n", NEW)

    captured = owned(AntigravityFetcher, root=home).fetch(tmp_path, since=datetime(2026, 9, 15, tzinfo=UTC))

    assert {"conv-old/.system_generated/logs/transcript_full.jsonl", "conv-old/report.md"} <= set(_paths(captured))


def test_fetch_antigravity_stamps_the_archive_before_listing_conversations(tmp_path, monkeypatch):
    """A conversation written between listing and stamping would otherwise fall between two fetches."""
    home = _antigravity_home(tmp_path)
    fetcher = owned(AntigravityFetcher, root=home)
    listed = []
    real_iterdir = Path.iterdir

    def iterdir(self):
        listed.append(datetime.now(UTC))
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    captured = fetcher.fetch(tmp_path, since=None)
    monkeypatch.undo()

    assert captured
    assert all(read_header(a).fetched_at <= listed[0] for a in captured)


def test_fetch_antigravity_with_nothing_fresh_returns_empty(tmp_path):
    fetcher = owned(AntigravityFetcher, root=_antigravity_home(tmp_path))

    assert fetcher.fetch(tmp_path, since=datetime(2026, 11, 1, tzinfo=UTC)) == []


def test_fetch_antigravity_without_antigravity_installed_returns_empty(tmp_path):
    assert owned(AntigravityFetcher, root=tmp_path / "absent").fetch(tmp_path, since=None) == []


def test_fetch_antigravity_root_follows_antigravity_home_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIGRAVITY_HOME", str(_antigravity_home(tmp_path)))

    captured = owned(AntigravityFetcher).fetch(tmp_path, since=None)

    assert _paths(captured) == sorted(EVERYTHING)


def test_fetch_antigravity_command_lands_conversations_in_one_commit(test_repo, tmp_path):
    before = len(git(test_repo.root, "log", "--oneline").splitlines())

    fetch(test_repo, sources=fetching(owned(AntigravityFetcher, root=_antigravity_home(tmp_path))))

    landed = sorted(p.relative_to(test_repo.root).as_posix() for p in (test_repo.root / "chats").rglob("*.md"))
    assert landed == [
        "chats/antigravity/2026/09/2026-09-01-old-work.md",
        "chats/antigravity/2026/10/2026-10-01-new-work.md",
    ]
    assert len(git(test_repo.root, "log", "--oneline").splitlines()) == before + 1
    message = git(test_repo.root, "log", "-1", "--format=%B")
    stored = [blob.path for blob in test_repo.blobs(*archive_names("antigravity"))]
    assert len(stored) == 2
    assert message.startswith("Fetch antigravity: 2 archives")
    assert all(path.as_posix() in message for path in stored)


def _entries(captured: list[Path]) -> list[dict]:
    return [e for a in captured for e in read_entries(a)]


def _paths(captured: list[Path]) -> list[str]:
    return sorted(e["path"] for e in _entries(captured))
