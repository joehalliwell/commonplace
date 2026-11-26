import json
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


def _archive(tmp_path: Path, *lines: dict, cid: str = "conv-1", extra: list[dict] | None = None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    entries = [
        {"endpoint": "file", "path": f"{cid}/.system_generated/logs/transcript_full.jsonl", "response": _jsonl(*lines)},
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
            "path": "conv-1/.system_generated/logs/transcript.jsonl",
            "response": _jsonl(_user("compact", "2026-11-25T08:10:00Z")),
        },
        {
            "endpoint": "file",
            "path": "conv-1/.system_generated/logs/transcript_full.jsonl",
            "response": _jsonl(_user("full", "2026-11-25T08:10:00Z")),
        },
        {
            "endpoint": "file",
            "path": "conv-1/.system_generated/logs/chunks/transcript_full/00000000.jsonl",
            "response": _jsonl(_user("chunk", "2026-11-25T08:10:00Z")),
        },
        {"endpoint": "file", "path": "conv-1/plan.md", "response": "# Plan\n"},
    ]
    archive = write_archive(tmp_path / "antigravity-wire.jsonl.xz", "antigravity", entries)

    [log] = owned(AntigravityImporter).import_(archive)

    assert [e.content for e in log.events] == ["full"]


def test_antigravity_import_falls_back_to_compact_transcript_when_full_is_absent(tmp_path):
    entries = [
        {
            "endpoint": "file",
            "path": "conv-1/.system_generated/logs/transcript.jsonl",
            "response": _jsonl(_user("compact only", "2026-11-25T08:10:00Z")),
        }
    ]
    archive = write_archive(tmp_path / "antigravity-wire.jsonl.xz", "antigravity", entries)

    [log] = owned(AntigravityImporter).import_(archive)

    assert [e.content for e in log.events] == ["compact only"]


def test_antigravity_import_drops_a_half_written_trailing_line(tmp_path):
    """An active session can end mid-line when captured; the next fetch captures the rest."""
    text = _jsonl(_user("hi", "2026-11-25T08:10:00Z")) + '{"step_index": 1, "type": "PLANNER'
    entry = {"endpoint": "file", "path": "conv-1/.system_generated/logs/transcript_full.jsonl", "response": text}
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


def test_antigravity_import_uses_conversation_metadata_for_title_and_skips_subagents(tmp_path):
    titled = _archive(
        tmp_path / "titled",
        _user("some prompt", "2026-11-25T08:10:00Z"),
        cid="conv-top",
        extra=[
            {
                "endpoint": "conversation",
                "cid": "conv-top",
                "response": json.dumps(
                    {
                        "id": "conv-top",
                        "metadata": {"projectId": "proj-1"},
                        "annotations": {"title": "PR review"},
                        "state": {"summary": "Fallback summary"},
                    }
                ),
            }
        ],
    )
    subagent = _archive(
        tmp_path / "sub",
        _user("research task", "2026-11-25T08:10:00Z"),
        cid="conv-child",
        extra=[
            {
                "endpoint": "conversation",
                "cid": "conv-child",
                "response": json.dumps({"id": "conv-child", "metadata": {"parentConversationId": "conv-top"}}),
            }
        ],
    )

    [log] = owned(AntigravityImporter).import_(titled)
    assert (log.title, log.metadata["project_id"]) == ("PR review", "proj-1")
    assert owned(AntigravityImporter).import_(subagent) == []


def test_antigravity_import_keeps_a_conversations_first_path_when_retitled(test_repo, tmp_path):
    first = _archive(tmp_path / "first", _user("initial title", "2026-11-25T08:10:00Z"), cid="conv-keep")
    second = _archive(
        tmp_path / "second",
        _user("initial title", "2026-11-25T08:10:00Z"),
        cid="conv-keep",
        extra=[
            {
                "endpoint": "conversation",
                "cid": "conv-keep",
                "response": json.dumps({"id": "conv-keep", "annotations": {"title": "Renamed title"}}),
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


@pytest.mark.parametrize("text", ["", '{"step_index": 0, "type": "GENERIC", "created_at": "2026-11-25T08:10:00Z"}\n'])
def test_antigravity_import_empty_conversation_returns_no_logs(tmp_path, text):
    entry = {"endpoint": "file", "path": "conv-empty/.system_generated/logs/transcript_full.jsonl", "response": text}
    archive = write_archive(tmp_path / "antigravity-wire.jsonl.xz", "antigravity", [entry])

    assert owned(AntigravityImporter).import_(archive) == []
