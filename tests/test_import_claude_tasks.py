"""Tests for the scheduled-run importer, driven by the committed example archive."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from commonplace._import._claude_tasks import ClaudeTasksImporter
from commonplace._import._commands import autodetect_importer
from commonplace._import._types import Message, Role, ToolCall

WIRE = Path(__file__).parent / "resources" / "wire"
EXAMPLE = WIRE / "claude-tasks-v3.jsonl.gz"


@pytest.fixture
def run():
    [log] = ClaudeTasksImporter().import_(EXAMPLE)
    return log


def test_claude_tasks_archive_is_claimed_by_its_own_importer():
    assert isinstance(autodetect_importer(EXAMPLE), ClaudeTasksImporter)


@pytest.mark.parametrize("other", ["claude-v3", "claude-memory-v3"])
def test_claude_tasks_importer_declines_other_claude_archives(other):
    assert not ClaudeTasksImporter().can_import(WIRE / f"{other}.jsonl.gz")


def test_claude_tasks_run_reads_in_sequence_order(run):
    """The API sends events newest first; the chat reads oldest first."""
    messages = [e for e in run.events if isinstance(e, Message)]
    assert [(m.sender, m.content) for m in messages] == [
        (Role.USER, "Find news."),
        (Role.AGENT, "[AI] Nothing new today"),
    ]


def test_claude_tasks_run_keeps_tool_calls_with_their_results(run):
    [call] = [e for e in run.events if isinstance(e, ToolCall)]
    assert (call.tool, call.args, call.output) == ("WebSearch", {"query": "news"}, "x")


def test_claude_tasks_run_title_drops_decoration_and_carries_the_time(run):
    """Twice-daily runs share a title and a date, so the time keeps their paths apart."""
    assert run.title == "Morning digest 05:10"
    assert run.created == datetime(2026, 10, 11, 5, 10, 31, 312825, tzinfo=UTC)


def test_claude_tasks_run_metadata_ties_it_to_its_task(run):
    assert run.metadata == {
        "session_id": "cse_01Example",
        "trigger_id": "trig_01Example",
        "resource": "https://claude.ai/code/session_01Example",
        "models": ["claude-opus-5-5"],
    }
