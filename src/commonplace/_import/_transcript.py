"""Shared transcript parsing and turn-formatting helpers for coding-agent importers."""

import json
import re
from collections.abc import Iterator
from typing import Any

from commonplace._import._types import Message, Role
from commonplace._logging import logger

_TOOL_LINE = 80


def tool_line(name: str, tool_input: dict[str, Any]) -> str:
    """A tool call as a list item: its name and first text argument, on one shortened line."""
    target = next((" ".join(v.split()) for v in tool_input.values() if isinstance(v, str) and v.strip()), None)
    if target is None:
        return f"- {name}"
    if len(target) > _TOOL_LINE:
        target = target[: _TOOL_LINE - 1] + "…"
    ticks = "`" * (max((len(run) for run in re.findall(r"`+", target)), default=0) + 1)
    pad = " " if target.startswith("`") or target.endswith("`") else ""
    return f"- {name}: {ticks}{pad}{target}{pad}{ticks}"


def joined(parts: list[str]) -> str:
    """Parts as paragraphs, but adjacent list items as one list."""
    out = parts[0]
    for part in parts[1:]:
        tight = out.rsplit("\n", 1)[-1].startswith("- ") and part.startswith("- ")
        out += ("\n" if tight else "\n\n") + part
    return out


def merged(events: list[Message]) -> list[Message]:
    """Consecutive agent records as one turn, as it was had: coding agents write each step as a record."""
    out: list[Message] = []
    for event in events:
        if out and event.sender == out[-1].sender == Role.AGENT:
            out[-1] = out[-1].model_copy(update={"content": joined([out[-1].content, event.content])})
        else:
            out.append(event)
    return out


def records(transcript: str, where: str) -> Iterator[dict[str, Any]]:
    """The transcript's JSONL lines, parsed; a session fetched while running can end mid-line, and the next fetch has it."""
    lines = [line for line in transcript.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            if i < len(lines) - 1:
                raise
            logger.warning(f"Dropping the half-written last line of {where}")
