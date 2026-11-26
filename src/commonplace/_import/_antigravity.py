"""Importer for the `antigravity-wire.jsonl.xz` archive [[AntigravityFetcher]] records.

Entries are `{"endpoint": "file", "path": "<app>/...", "response": ...}`, recording each conversation's `brain/<cid>/`
tree, `conversations/<cid>.{db,pb}`, `annotations/<cid>.pbtxt`, and the app's `conversation_summaries.db` verbatim.
Notes are rendered from `brain/<cid>/.system_generated/logs/transcript_full.jsonl` (falling back to `transcript.jsonl`),
titled from `annotations/<cid>.pbtxt` or `conversation_summaries.db` else the first prompt; subagent child conversations
are skipped, and thinking, tool outputs, harness messages, databases and artefacts stay in the archive.
"""

import re
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from textwrap import shorten
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._transcript import joined, merged, records, tool_line
from commonplace._import._types import EventLog, Message, Role, models_field
from commonplace._logging import logger
from commonplace._wire import entry_body, read_entries

_FULL_TRANSCRIPT = ".system_generated/logs/transcript_full.jsonl"
_COMPACT_TRANSCRIPT = ".system_generated/logs/transcript.jsonl"
_USER_REQUEST = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)
_HARNESS_BLOCKS = re.compile(
    r"<(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>.*?</(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>",
    re.DOTALL,
)
_PBTXT_TITLE = re.compile(r'^\s*title\s*:\s*"((?:[^"\\]|\\.)*)"', re.MULTILINE)
_PBTXT_ESCAPE = re.compile(r'\\([0-7]{3}|["\\nrt])')
_SIMPLE_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}


@dataclass
class _Summary:
    title: str = ""
    parent_conversation_id: str = ""
    project_id: str = ""


class AntigravityImporter(BaseWireImporter):
    """Importer for local Antigravity conversation archives."""

    name: str = "Antigravity"
    id_key: str | None = "conversation_id"

    def import_(self, path: Path) -> list[EventLog]:
        transcripts: dict[str, tuple[str, str]] = {}
        annotation_titles: dict[str, str] = {}
        summaries: dict[str, _Summary] = {}

        for entry in read_entries(path):
            if entry.get("endpoint") != "file" or "path" not in entry:
                continue
            parts = PurePosixPath(entry["path"]).parts
            if not parts:
                continue
            if parts[-1] == "conversation_summaries.db":
                summaries.update(_read_summaries(entry_body(entry)))
                continue
            if len(parts) >= 2 and parts[-2] == "annotations" and parts[-1].endswith(".pbtxt"):
                if title := _parse_pbtxt_title(entry_body(entry).decode("utf-8", errors="replace")):
                    annotation_titles[parts[-1].removesuffix(".pbtxt")] = title
                continue
            if (found := _transcript_ref(parts)) is not None:
                cid, inner = found
                if inner == _FULL_TRANSCRIPT or (inner == _COMPACT_TRANSCRIPT and cid not in transcripts):
                    transcripts[cid] = (entry["path"], entry_body(entry).decode("utf-8"))

        return [
            log
            for cid, (where, text) in transcripts.items()
            if (log := self._conversation(cid, text, where, annotation_titles.get(cid), summaries.get(cid))) is not None
        ]

    def _conversation(
        self, cid: str, transcript: str, where: str, annotation_title: str | None, summary: _Summary | None
    ) -> EventLog | None:
        """One conversation's transcript as a chat, or None if it is a subagent child or holds no turns."""
        if summary and summary.parent_conversation_id:
            logger.info(f"Skipping {where}: subagent of {summary.parent_conversation_id}")
            return None

        ordered: list[tuple[int, Message]] = []
        models: list[str | None] = []

        for index, data in enumerate(records(transcript, where)):
            if data.get("type") == "PLANNER_RESPONSE" and (model := data.get("model")):
                models.append(model)
            if message := _process_record(data):
                step = data.get("step_index")
                ordered.append((step if isinstance(step, int) else index, message))

        events = merged([msg for _, msg in sorted(ordered, key=lambda item: item[0])])
        if not events:
            logger.warning(f"No messages found in {where}")
            return None

        prompt = next((e.content.strip() for e in events if e.sender == Role.USER), "")
        first_line = shorten(prompt.splitlines()[0], 60, placeholder="…") if prompt else None
        summary_title = summary.title.strip() if summary else ""
        title = (annotation_title or "").strip() or summary_title or first_line or cid

        metadata: dict[str, Any] = {"conversation_id": cid}
        if summary and summary.project_id:
            metadata["project_id"] = summary.project_id
        metadata |= models_field(models)

        return EventLog(created=events[0].created, events=events, title=title, metadata=metadata)


def _transcript_ref(parts: tuple[str, ...]) -> tuple[str, str] | None:
    """`(cid, relative_path)` if `parts` points inside `.../brain/<cid>/...`, else None."""
    try:
        brain = parts.index("brain")
    except ValueError:
        return None
    if len(parts) <= brain + 2:
        return None
    return parts[brain + 1], "/".join(parts[brain + 2 :])


@contextmanager
def _open_sqlite_bytes(raw: bytes) -> Iterator[sqlite3.Connection]:
    """Open a SQLite database stored as bytes, falling back to a temp file if its header marks WAL mode."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.deserialize(raw)
        # `deserialize` defers header validation until the first query, where a WAL-mode header fails in `:memory:`.
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
    except sqlite3.Error:
        conn.close()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "db.sqlite"
            path.write_bytes(raw)
            with closing(sqlite3.connect(path)) as disk:
                yield disk
        return
    with closing(conn):
        yield conn


def _read_summaries(raw: bytes) -> dict[str, _Summary]:
    """Read conversation titles, parents and project ids from a snapshotted `conversation_summaries.db`."""
    found: dict[str, _Summary] = {}
    try:
        with _open_sqlite_bytes(raw) as conn:
            tables = {name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if "conversation_summaries" in tables:
                cols = {row[1] for row in conn.execute("PRAGMA table_info(conversation_summaries)")}
                if "conversation_id" in cols:
                    title_col = "title" if "title" in cols else "''"
                    parent_col = "parent_conversation_id" if "parent_conversation_id" in cols else "''"
                    project_col = "project_id" if "project_id" in cols else "''"
                    query = (
                        f"SELECT conversation_id, {title_col}, {parent_col}, {project_col} FROM conversation_summaries"
                    )
                    for cid, title, parent, project in conn.execute(query):
                        found[str(cid)] = _Summary(str(title or ""), str(parent or ""), str(project or ""))
    except sqlite3.Error as exc:
        logger.warning(f"Could not read conversation_summaries.db: {exc}")
    return found


def _parse_pbtxt_title(text: str) -> str | None:
    """Extract the `title` string from an `annotations/<cid>.pbtxt` protobuf text file."""
    match = _PBTXT_TITLE.search(text)
    if not match:
        return None
    raw = match.group(1)
    # Protobuf text format encodes non-ASCII bytes as octal escapes (\342\200\224); decode via latin-1 -> utf-8.
    unescaped = _PBTXT_ESCAPE.sub(
        lambda m: _SIMPLE_ESCAPES[m[1]] if m[1] in _SIMPLE_ESCAPES else chr(int(m[1], 8)),
        raw,
    )
    try:
        return unescaped.encode("latin-1").decode("utf-8").strip() or None
    except UnicodeError:
        return unescaped.strip() or None


def _process_record(data: dict[str, Any]) -> Message | None:
    """One transcript line as a turn: user request, or agent prose and tool-call lines; outputs stay in the archive."""
    raw_created = data.get("created_at")
    if not raw_created:
        return None
    created = datetime.fromisoformat(raw_created)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    kind = data.get("type")

    if kind == "USER_INPUT":
        if data.get("source") != "USER_EXPLICIT":
            return None
        if text := _user_text(str(data.get("content") or "")):
            return Message(sender=Role.USER, content=text, created=created)
        return None

    if kind == "PLANNER_RESPONSE":
        parts: list[str] = []
        if content := str(data.get("content") or "").strip():
            parts.append(content)
        for call in data.get("tool_calls") or []:
            if isinstance(call, dict) and (name := call.get("name")):
                args = call.get("args")
                parts.append(tool_line(str(name), args if isinstance(args, dict) else {}))
        return Message(sender=Role.AGENT, content=joined(parts), created=created) if parts else None

    return None


def _user_text(content: str) -> str:
    """The prompt the user typed, stripped of the harness's `<USER_REQUEST>` and metadata wrappers."""
    if match := _USER_REQUEST.search(content):
        return match.group(1).strip()
    return _HARNESS_BLOCKS.sub("", content).strip()
