import json
import os
import sqlite3
from contextlib import closing
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


def _write_conv_db(path: Path, cid: str, modified: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE trajectory_meta (trajectory_id TEXT PRIMARY KEY, cascade_id TEXT)")
        conn.execute("INSERT INTO trajectory_meta VALUES (?, ?)", (f"traj-{cid}", cid))
        conn.commit()
    os.utime(path, (modified.timestamp(), modified.timestamp()))
    return path


def _write_summaries_db(path: Path, rows_data: list[tuple[str, str, str, str]], modified: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "CREATE TABLE conversation_summaries ("
            "conversation_id TEXT PRIMARY KEY, title TEXT, parent_conversation_id TEXT, project_id TEXT)"
        )
        conn.executemany("INSERT INTO conversation_summaries VALUES (?, ?, ?, ?)", rows_data)
        conn.commit()
    os.utime(path, (modified.timestamp(), modified.timestamp()))
    return path


#: Every file captured from `_antigravity_roots` since the epoch, across both CLI and IDE app-data dirs.
CLI_NEW = [
    "antigravity-cli/annotations/conv-new.pbtxt",
    "antigravity-cli/brain/conv-new/.system_generated/logs/transcript.jsonl",
    "antigravity-cli/brain/conv-new/.system_generated/logs/transcript_full.jsonl",
    "antigravity-cli/brain/conv-new/.system_generated/steps/1/output.txt",
    "antigravity-cli/brain/conv-new/.user_uploaded/shot.png",
    "antigravity-cli/brain/conv-new/plan.md",
    "antigravity-cli/brain/conv-new/scratch/notes.txt",
    "antigravity-cli/conversations/conv-new.db",
]
CLI_OLD = [
    "antigravity-cli/brain/conv-old/.system_generated/logs/transcript_full.jsonl",
    "antigravity-cli/conversations/conv-old.db",
]
CLI_SUB = [
    "antigravity-cli/brain/conv-sub/.system_generated/logs/transcript_full.jsonl",
]
IDE_CONV = [
    "antigravity/brain/ide-1/task.md",
    "antigravity/conversations/ide-1.pb",
]
SUMMARIES = ["antigravity-cli/conversation_summaries.db"]
EVERYTHING = sorted([*CLI_NEW, *CLI_OLD, *CLI_SUB, *IDE_CONV, *SUMMARIES])


def _antigravity_roots(tmp_path: Path) -> list[Path]:
    """Both `~/.gemini/antigravity-cli` and `~/.gemini/antigravity` with CLI, subagent and IDE conversations."""
    cli = tmp_path / ".gemini" / "antigravity-cli"
    ide = tmp_path / ".gemini" / "antigravity"

    _write(
        cli / "brain" / "conv-old" / ".system_generated" / "logs" / "transcript_full.jsonl",
        _transcript("old work", "Done.", "2026-09-01T10:00:00Z"),
        OLD,
    )
    _write_conv_db(cli / "conversations" / "conv-old.db", "conv-old", OLD)

    _write(
        cli / "brain" / "conv-new" / ".system_generated" / "logs" / "transcript_full.jsonl",
        _transcript("new work", "On it.", "2026-10-01T10:00:00Z"),
        NEW,
    )
    _write(
        cli / "brain" / "conv-new" / ".system_generated" / "logs" / "transcript.jsonl",
        _transcript("new work", "On it.", "2026-10-01T10:00:00Z"),
        NEW,
    )
    _write(cli / "brain" / "conv-new" / ".system_generated" / "steps" / "1" / "output.txt", "line one\r\nline two", NEW)
    _write(cli / "brain" / "conv-new" / ".user_uploaded" / "shot.png", PNG, NEW)
    _write(cli / "brain" / "conv-new" / "plan.md", "# Plan\n", NEW)
    _write(cli / "brain" / "conv-new" / "scratch" / "notes.txt", "scratch\n", NEW)
    _write(cli / "annotations" / "conv-new.pbtxt", 'title:"Fresh Work"\n', NEW)
    _write_conv_db(cli / "conversations" / "conv-new.db", "conv-new", NEW)

    _write(
        cli / "brain" / "conv-sub" / ".system_generated" / "logs" / "transcript_full.jsonl",
        _transcript("subagent task", "Subagent done.", "2026-10-01T10:01:00Z"),
        NEW,
    )
    _write_summaries_db(
        cli / "conversation_summaries.db",
        [
            ("conv-old", "Old Summary Title", "", "proj-a"),
            ("conv-new", "New Summary Title", "", "proj-b"),
            ("conv-sub", "Subagent", "conv-new", "proj-b"),
            ("ide-1", "IDE Session", "", ""),
        ],
        NEW,
    )

    _write(ide / "brain" / "ide-1" / "task.md", "# Task\n", NEW)
    _write(ide / "conversations" / "ide-1.pb", b"\x08\x01\x12\x05hello", NEW)
    return [cli, ide]


def test_fetch_antigravity_records_every_file_across_both_roots_verbatim(tmp_path):
    """Capture is total and dumb: brain trees, databases, protobufs, annotations and summaries are all kept."""
    roots = _antigravity_roots(tmp_path)

    [archive] = owned(AntigravityFetcher, roots=roots).fetch(tmp_path, since=None)

    assert read_header(archive).source == "antigravity"
    entries = list(read_entries(archive))
    assert sorted((e["endpoint"], e["path"]) for e in entries) == [("file", path) for path in EVERYTHING]
    assert [e["path"] for e in entries].count("antigravity-cli/conversation_summaries.db") == 1
    by_root = {r.name: r for r in roots}
    for entry in entries:
        app, rel = entry["path"].split("/", 1)
        disk = by_root[app] / rel
        if disk.suffix == ".db":
            with closing(sqlite3.connect(":memory:")) as conn:
                conn.deserialize(entry_body(entry))
                assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        else:
            assert entry_body(entry) == disk.read_bytes()


def test_fetch_antigravity_snapshots_uncheckpointed_wal_frames_and_tracks_wal_mtime(tmp_path):
    """Antigravity keeps SQLite DBs in WAL mode; uncommitted-to-main-file WAL frames must land in the snapshot."""
    cli = tmp_path / "antigravity-cli"
    _write(
        cli / "brain" / "c1" / ".system_generated" / "logs" / "transcript_full.jsonl",
        _transcript("hi", "hello", "2026-09-01T10:00:00Z"),
        OLD,
    )
    db_path = _write_conv_db(cli / "conversations" / "c1.db", "c1", OLD)
    # Keep a reader open so the subsequent write stays in `-wal` rather than auto-checkpointing into `.db`.
    with closing(sqlite3.connect(db_path)) as reader, closing(sqlite3.connect(db_path)) as writer:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM trajectory_meta").fetchall()
        writer.execute("INSERT INTO trajectory_meta VALUES ('traj-wal', 'from-wal')")
        writer.commit()
        wal = db_path.with_name(f"{db_path.name}-wal")
        assert wal.is_file()
        os.utime(db_path, (OLD.timestamp(), OLD.timestamp()))
        os.utime(wal, (NEW.timestamp(), NEW.timestamp()))

        [archive] = owned(AntigravityFetcher, root=cli).fetch(tmp_path, since=datetime(2026, 9, 15, tzinfo=UTC))

    [db_entry] = [e for e in read_entries(archive) if e["path"] == "antigravity-cli/conversations/c1.db"]
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.deserialize(entry_body(db_entry))
        rows_found = conn.execute("SELECT cascade_id FROM trajectory_meta ORDER BY trajectory_id").fetchall()
    assert rows_found == [("c1",), ("from-wal",)]


def test_fetch_antigravity_counts_every_file_it_records_on_the_sources_row(tmp_path):
    fetcher = owned(AntigravityFetcher, roots=_antigravity_roots(tmp_path))

    with rows(["antigravity"]) as table, on(table["antigravity"]):
        captured = fetcher.fetch(tmp_path, since=NEW - (NEW - OLD) / 2)

        assert table["antigravity"].done()[0] == len(_entries(captured))


def test_fetch_antigravity_incremental_reads_conversations_changed_after_the_cursor(tmp_path):
    captured = owned(AntigravityFetcher, roots=_antigravity_roots(tmp_path)).fetch(
        tmp_path, since=datetime(2026, 9, 15, tzinfo=UTC)
    )

    assert _paths(captured) == sorted([*CLI_NEW, *CLI_SUB, *IDE_CONV, *SUMMARIES])


def test_fetch_antigravity_conversation_whose_annotation_changed_is_read_again(tmp_path):
    roots = _antigravity_roots(tmp_path)
    _write(roots[0] / "annotations" / "conv-old.pbtxt", 'title:"Renamed"\n', NEW)

    captured = owned(AntigravityFetcher, roots=roots).fetch(tmp_path, since=datetime(2026, 9, 15, tzinfo=UTC))

    assert {
        "antigravity-cli/brain/conv-old/.system_generated/logs/transcript_full.jsonl",
        "antigravity-cli/conversations/conv-old.db",
        "antigravity-cli/annotations/conv-old.pbtxt",
    } <= set(_paths(captured))


def test_fetch_antigravity_stamps_the_archive_before_listing_conversations(tmp_path, monkeypatch):
    """A conversation written between listing and stamping would otherwise fall between two fetches."""
    roots = _antigravity_roots(tmp_path)
    fetcher = owned(AntigravityFetcher, roots=roots)
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
    fetcher = owned(AntigravityFetcher, roots=_antigravity_roots(tmp_path))

    assert fetcher.fetch(tmp_path, since=datetime(2026, 11, 1, tzinfo=UTC)) == []


def test_fetch_antigravity_without_antigravity_installed_returns_empty(tmp_path):
    assert owned(AntigravityFetcher, root=tmp_path / "absent").fetch(tmp_path, since=None) == []


def test_fetch_antigravity_root_follows_antigravity_home_env(tmp_path, monkeypatch):
    roots = _antigravity_roots(tmp_path)
    monkeypatch.setenv("ANTIGRAVITY_HOME", os.pathsep.join(str(r) for r in roots))

    captured = owned(AntigravityFetcher).fetch(tmp_path, since=None)

    assert _paths(captured) == EVERYTHING


def test_fetch_antigravity_command_lands_conversations_in_one_commit_with_real_titles_and_no_subagents(
    test_repo, tmp_path
):
    before = len(git(test_repo.root, "log", "--oneline").splitlines())

    fetch(test_repo, sources=fetching(owned(AntigravityFetcher, roots=_antigravity_roots(tmp_path))))

    landed = sorted(p.relative_to(test_repo.root).as_posix() for p in (test_repo.root / "chats").rglob("*.md"))
    # conv-old titled from conversation_summaries.db, conv-new from annotations pbtxt; conv-sub skipped; ide-1 kept in blob.
    assert landed == [
        "chats/antigravity/2026/09/2026-09-01-old-summary-title.md",
        "chats/antigravity/2026/10/2026-10-01-fresh-work.md",
    ]
    assert len(git(test_repo.root, "log", "--oneline").splitlines()) == before + 1
    message = git(test_repo.root, "log", "-1", "--format=%B")
    [blob] = test_repo.blobs(*archive_names("antigravity"))
    assert message.startswith(f"Fetch antigravity: {blob.path.as_posix()}")


def _entries(captured: list[Path]) -> list[dict]:
    return [e for a in captured for e in read_entries(a)]


def _paths(captured: list[Path]) -> list[str]:
    return sorted(e["path"] for e in _entries(captured))
