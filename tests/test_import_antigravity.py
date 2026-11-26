import base64
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commonplace._import._antigravity import AntigravityImporter
from commonplace._import._commands import autodetect_importer, import_
from commonplace._import._types import Role
from commonplace._sources import importers
from commonplace._types import ChatSource
from commonplace._wire import write_archive
from tests.fetching import owned


def _jsonl(*lines: dict) -> str:
    return "".join(json.dumps(line) + "\n" for line in lines)


def _user(
    content: str,
    created_at: str = "2026-11-25T08:10:00Z",
    *,
    step_index: int = 0,
    source: str = "USER_EXPLICIT",
    wrap: bool = True,
) -> dict:
    wrapped = (
        f"<USER_REQUEST>\n{content}\n</USER_REQUEST>\n"
        f"<ADDITIONAL_METADATA>\nThe current local time is: {created_at}.\n</ADDITIONAL_METADATA>"
        if wrap
        else content
    )
    return {
        "step_index": step_index,
        "source": source,
        "type": "USER_INPUT",
        "status": "DONE",
        "created_at": created_at,
        "content": wrapped,
    }


def _planner(
    created_at: str = "2026-11-25T08:10:01Z",
    *,
    step_index: int = 1,
    content: str = "",
    thinking: str = "",
    tool_calls: list[dict] | None = None,
    model: str = "gemini-4-neon-high",
) -> dict:
    record: dict = {
        "step_index": step_index,
        "source": "MODEL",
        "type": "PLANNER_RESPONSE",
        "status": "DONE",
        "created_at": created_at,
        "model": model,
    }
    if content:
        record["content"] = content
    if thinking:
        record["thinking"] = thinking
    if tool_calls is not None:
        record["tool_calls"] = tool_calls
    return record


def _summaries_entry(rows_data: list[tuple[str, str, str, str]], *, app: str = "antigravity-cli") -> dict:
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.execute(
            "CREATE TABLE conversation_summaries ("
            "conversation_id TEXT PRIMARY KEY, title TEXT, parent_conversation_id TEXT, project_id TEXT)"
        )
        conn.executemany("INSERT INTO conversation_summaries VALUES (?, ?, ?, ?)", rows_data)
        raw = conn.serialize()
    return {
        "endpoint": "file",
        "path": f"{app}/conversation_summaries.db",
        "response": base64.b64encode(raw).decode(),
        "encoding": "base64",
    }


def _archive(tmp_path: Path, *lines: dict, cid: str = "conv-1", extra: list[dict] | None = None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "endpoint": "file",
            "path": f"antigravity-cli/brain/{cid}/.system_generated/logs/transcript_full.jsonl",
            "response": _jsonl(*lines),
        },
        *(extra or []),
    ]
    return write_archive(tmp_path / "antigravity-wire.jsonl.xz", "antigravity", entries)


def test_antigravity_import_renders_user_requests_agent_prose_and_tool_calls(tmp_path):
    archive = _archive(
        tmp_path,
        _user("Check the repo status.", "2026-11-25T08:10:00Z", step_index=0),
        _planner(
            "2026-11-25T08:10:00Z",
            step_index=1,
            thinking="Let me read the file and run git status.",
            tool_calls=[
                {"name": "read_file", "args": {"Path": "/work/README.md"}},
                {"name": "run_command", "args": {"CommandLine": "git status", "WaitMsBeforeAsync": 5000}},
                {"name": "update_steps", "args": {"steps": []}},
            ],
        ),
        {
            "step_index": 2,
            "source": "MODEL",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": "2026-11-25T08:10:01Z",
            "content": "On branch main\nnothing to commit",
        },
        {
            "step_index": 3,
            "source": "SYSTEM",
            "type": "SYSTEM_MESSAGE",
            "status": "DONE",
            "created_at": "2026-11-25T08:10:01Z",
            "content": "Reminder: work efficiently.",
        },
        _planner("2026-11-25T08:10:02Z", step_index=4, thinking="All clean.", content="Working tree is clean."),
    )

    [log] = owned(AntigravityImporter).import_(archive)

    assert [(e.sender, e.content) for e in log.events] == [
        (Role.USER, "Check the repo status."),
        (
            Role.AGENT,
            "- read_file: `/work/README.md`\n- run_command: `git status`\n- update_steps\n\nWorking tree is clean.",
        ),
    ]
    assert log.created == datetime(2026, 11, 25, 8, 10, 0, tzinfo=UTC)
    assert log.title == "Check the repo status."
    assert log.metadata == {"conversation_id": "conv-1", "models": ["gemini-4-neon-high"]}


def test_antigravity_import_sorts_by_step_index_and_handles_naive_timestamps(tmp_path):
    """`step_index` is the authoritative order; naive timestamps normalize to UTC rather than crashing."""
    archive = _archive(
        tmp_path,
        _planner("2026-11-25T08:10:00", step_index=1, content="Second"),
        _user("First", "2026-11-25T08:10:01Z", step_index=0),
    )

    [log] = owned(AntigravityImporter).import_(archive)

    assert [(e.sender, e.content) for e in log.events] == [(Role.USER, "First"), (Role.AGENT, "Second")]
    assert all(e.created.tzinfo is not None for e in log.events)


def test_antigravity_import_unwraps_plain_user_input_and_drops_settings_metadata(tmp_path):
    plain = _user(
        "Hello there\n<USER_SETTINGS_CHANGE>\nSwitched model.\n</USER_SETTINGS_CHANGE>",
        "2026-11-25T08:10:00Z",
        wrap=False,
    )
    archive = _archive(tmp_path, plain, _planner("2026-11-25T08:10:01Z", content="Hi!"))

    [log] = owned(AntigravityImporter).import_(archive)

    assert [(e.sender, e.content) for e in log.events] == [(Role.USER, "Hello there"), (Role.AGENT, "Hi!")]


def test_antigravity_import_skips_thinking_only_steps_and_non_explicit_user_inputs(tmp_path):
    archive = _archive(
        tmp_path,
        _user("injected prompt", "2026-11-25T08:10:00Z", step_index=0, source="SYSTEM"),
        _planner("2026-11-25T08:10:01Z", step_index=1, thinking="Only thinking."),
        _planner("2026-11-25T08:10:02Z", step_index=2, content="Spoken."),
    )

    [log] = owned(AntigravityImporter).import_(archive)

    assert [(e.sender, e.content) for e in log.events] == [(Role.AGENT, "Spoken.")]
    assert log.title == "conv-1"


def test_antigravity_import_prefers_full_transcript_and_ignores_chunks_and_artefacts(tmp_path):
    entries = [
        {
            "endpoint": "file",
            "path": "antigravity-cli/brain/conv-1/.system_generated/logs/transcript.jsonl",
            "response": _jsonl(_user("compact", "2026-11-25T08:10:00Z")),
        },
        {
            "endpoint": "file",
            "path": "antigravity-cli/brain/conv-1/.system_generated/logs/transcript_full.jsonl",
            "response": _jsonl(_user("full", "2026-11-25T08:10:00Z")),
        },
        {
            "endpoint": "file",
            "path": "antigravity-cli/brain/conv-1/.system_generated/logs/chunks/transcript_full/00000000.jsonl",
            "response": _jsonl(_user("chunk", "2026-11-25T08:10:00Z")),
        },
        {"endpoint": "file", "path": "antigravity-cli/brain/conv-1/plan.md", "response": "# Plan\n"},
        {
            "endpoint": "file",
            "path": "antigravity/conversations/ide-1.pb",
            "response": "CAESBQ==",
            "encoding": "base64",
        },
    ]
    archive = write_archive(tmp_path / "antigravity-wire.jsonl.xz", "antigravity", entries)

    [log] = owned(AntigravityImporter).import_(archive)

    assert [e.content for e in log.events] == ["full"]


def test_antigravity_import_falls_back_to_compact_transcript_when_full_is_absent(tmp_path):
    entries = [
        {
            "endpoint": "file",
            "path": "antigravity-cli/brain/conv-1/.system_generated/logs/transcript.jsonl",
            "response": _jsonl(_user("compact only", "2026-11-25T08:10:00Z")),
        }
    ]
    archive = write_archive(tmp_path / "antigravity-wire.jsonl.xz", "antigravity", entries)

    [log] = owned(AntigravityImporter).import_(archive)

    assert [e.content for e in log.events] == ["compact only"]


def test_antigravity_import_drops_a_half_written_trailing_line(tmp_path):
    """An active session can end mid-line when captured; the next fetch captures the rest."""
    text = _jsonl(_user("hi", "2026-11-25T08:10:00Z")) + '{"step_index": 1, "type": "PLANNER'
    entry = {
        "endpoint": "file",
        "path": "antigravity-cli/brain/conv-1/.system_generated/logs/transcript_full.jsonl",
        "response": text,
    }
    archive = write_archive(tmp_path / "antigravity-wire.jsonl.xz", "antigravity", [entry])

    [log] = owned(AntigravityImporter).import_(archive)

    assert [e.content for e in log.events] == ["hi"]


def test_antigravity_import_records_each_model_once_in_order(tmp_path):
    archive = _archive(
        tmp_path,
        _user("hi", "2026-11-25T08:10:00Z", step_index=0),
        _planner("2026-11-25T08:10:01Z", step_index=1, content="one", model="gemini-4-flash"),
        _planner("2026-11-25T08:10:02Z", step_index=2, content="two", model="gemini-4-neon-high"),
        _planner("2026-11-25T08:10:03Z", step_index=3, content="three", model="gemini-4-flash"),
    )

    [log] = owned(AntigravityImporter).import_(archive)

    assert log.metadata["models"] == ["gemini-4-flash", "gemini-4-neon-high"]


def test_antigravity_import_shortens_a_long_first_prompt_for_the_title(tmp_path):
    prompt = "Why is the build red after the dependency bump that landed on main this morning?\nLogs below."
    archive = _archive(tmp_path, _user(prompt, "2026-11-25T08:10:00Z"))

    [log] = owned(AntigravityImporter).import_(archive)

    assert log.title == "Why is the build red after the dependency bump that landed…"


def test_antigravity_import_reads_titles_projects_and_subagents_from_captured_files(tmp_path):
    """Annotations pbtxt beats summary title; subagent children are skipped."""
    entries = [
        {
            "endpoint": "file",
            "path": "antigravity-cli/brain/conv-ann/.system_generated/logs/transcript_full.jsonl",
            "response": _jsonl(_user("prompt one", "2026-11-25T08:10:00Z")),
        },
        {
            "endpoint": "file",
            "path": "antigravity-cli/annotations/conv-ann.pbtxt",
            "response": 'title:"PR \\"351\\" \\342\\200\\224 Review"\n',
        },
        {
            "endpoint": "file",
            "path": "antigravity-cli/brain/conv-sum/.system_generated/logs/transcript_full.jsonl",
            "response": _jsonl(_user("prompt two", "2026-11-25T08:11:00Z")),
        },
        {
            "endpoint": "file",
            "path": "antigravity-cli/brain/conv-sub/.system_generated/logs/transcript_full.jsonl",
            "response": _jsonl(_user("sub one", "2026-11-25T08:12:00Z")),
        },
        _summaries_entry(
            [
                ("conv-ann", "Summary Fallback", "", "proj-1"),
                ("conv-sum", "Summary Title", "", "proj-2"),
                ("conv-sub", "Sub 1", "conv-ann", "proj-1"),
            ],
        ),
    ]
    archive = write_archive(tmp_path / "antigravity-wire.jsonl.xz", "antigravity", entries)

    logs = owned(AntigravityImporter).import_(archive)

    assert [(log.metadata["conversation_id"], log.title, log.metadata["project_id"]) for log in logs] == [
        ("conv-ann", 'PR "351" — Review', "proj-1"),
        ("conv-sum", "Summary Title", "proj-2"),
    ]


def test_antigravity_import_keeps_a_conversations_first_path_when_retitled(test_repo, tmp_path):
    first = _archive(tmp_path / "first", _user("initial title", "2026-11-25T08:10:00Z"), cid="conv-keep")
    second = _archive(
        tmp_path / "second",
        _user("initial title", "2026-11-25T08:10:00Z"),
        cid="conv-keep",
        extra=[
            {
                "endpoint": "file",
                "path": "antigravity-cli/annotations/conv-keep.pbtxt",
                "response": 'title:"Renamed Title"\n',
            }
        ],
    )

    import_(first, test_repo, user="Joe")
    import_(second, test_repo, user="Joe")

    paths = sorted(p.relative_to(test_repo.root).as_posix() for p in (test_repo.root / "chats").rglob("*.md"))
    assert paths == ["chats/antigravity/2026/11/2026-11-25-initial-title.md"]


def test_antigravity_raw_transcript_is_left_to_fetch(tmp_path):
    raw = tmp_path / "transcript_full.jsonl"
    raw.write_text(_jsonl(_user("hi", "2026-11-25T08:10:00Z")))

    assert autodetect_importer(raw, importers(ChatSource)) is None


def test_antigravity_import_reads_wal_mode_summaries_db_bytes(tmp_path):
    """Even a raw WAL-mode `conversation_summaries.db` snapshot in an archive reads cleanly."""
    wal_db = tmp_path / "conversation_summaries.db"
    with closing(sqlite3.connect(wal_db)) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "CREATE TABLE conversation_summaries ("
            "conversation_id TEXT PRIMARY KEY, title TEXT, parent_conversation_id TEXT, project_id TEXT)"
        )
        conn.execute("INSERT INTO conversation_summaries VALUES ('conv-1', 'From WAL', '', 'proj-wal')")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    entry = {
        "endpoint": "file",
        "path": "antigravity-cli/conversation_summaries.db",
        "response": base64.b64encode(wal_db.read_bytes()).decode(),
        "encoding": "base64",
    }
    archive = _archive(tmp_path / "a", _user("hello", "2026-11-25T08:10:00Z"), cid="conv-1", extra=[entry])

    [log] = owned(AntigravityImporter).import_(archive)

    assert (log.title, log.metadata["project_id"]) == ("From WAL", "proj-wal")


@pytest.mark.parametrize("text", ["", '{"step_index": 0, "type": "GENERIC", "created_at": "2026-11-25T08:10:00Z"}\n'])
def test_antigravity_import_empty_conversation_returns_no_logs(tmp_path, text):
    entry = {
        "endpoint": "file",
        "path": "antigravity-cli/brain/conv-empty/.system_generated/logs/transcript_full.jsonl",
        "response": text,
    }
    archive = write_archive(tmp_path / "antigravity-wire.jsonl.xz", "antigravity", [entry])

    assert owned(AntigravityImporter).import_(archive) == []
