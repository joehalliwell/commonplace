"""Importer for the raw `batchexecute` wire log produced by [[GeminiFetcher]].

The archive is a `.jsonl` file, one line per RPC call:

    {"rpc": "MaZiqc", "payload": [...], "response": "<raw batchexecute text>"}
    {"rpc": "hNvQHb", "payload": [cid, ...], "response": "..."}
    ...

`MaZiqc` (list_chats) responses supply per-chat metadata (title, is_pinned,
updated_at). `hNvQHb` (read_chat) responses supply the turns. The importer
walks both to reconstruct `EventLog`s.

Deliberately fail-loud: if a wire slot moves, we want a KeyError/IndexError,
not silent field loss. The two known recoverable states — blocked candidates
and empty per-chat bodies — are the only ones we tolerate, with warnings.
"""

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from commonplace._import._types import EventLog, Message, Role
from commonplace._logging import logger

BATCH_PREAMBLE = ")]}'\n"


class GeminiImporter:
    """Consumes gemini-wire.jsonl emitted by the fetcher."""

    source: str = "gemini"

    def required_paths(self) -> list[str]:
        return []

    def can_import(self, path: Path) -> bool:
        if not path.name.endswith(".jsonl.gz"):
            return False
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                first = f.readline()
        except (OSError, gzip.BadGzipFile):
            return False
        if not first:
            return False
        try:
            entry = json.loads(first)
        except json.JSONDecodeError:
            return False
        return isinstance(entry, dict) and entry.get("rpc") in {"MaZiqc", "hNvQHb"}

    def import_(self, path: Path) -> list[EventLog]:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]

        # Pass 1: build cid → summary from every list_chats response.
        summaries: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if entry["rpc"] != "MaZiqc":
                continue
            body = _extract_rpc_body(entry["response"], "MaZiqc")
            if body is None:
                continue
            payload = entry["payload"]
            pinned = bool(payload[2][0])
            for row in body[2]:
                seconds, nanos = row[5]
                summaries[row[0]] = {
                    "cid": row[0],
                    "title": row[1],
                    "is_pinned": pinned,
                    "updated_at": _ts_to_iso(seconds, nanos),
                }

        # Pass 2: for each read_chat, reconstruct an EventLog from the wire
        # + the summary looked up by cid.
        logs: list[EventLog] = []
        for entry in entries:
            if entry["rpc"] != "hNvQHb":
                continue
            cid = entry["payload"][0]
            summary = summaries.get(cid)
            if summary is None:
                logger.warning(f"read_chat for {cid} has no matching list_chats entry; skipping")
                continue
            body = _extract_rpc_body(entry["response"], "hNvQHb")
            logs.append(_to_log(summary, body))
        return logs


def _to_log(summary: dict[str, Any], body: list | None) -> EventLog:
    """Build an EventLog from a summary + a read_chat body. `body` may be None
    for per-chat access glitches; the log is emitted with no events."""
    events: list[Message] = []
    gem_name: str | None = None

    if body is not None:
        wire_turns = body[0]
        # Wire returns newest-first; reverse to chronological.
        for turn in reversed(wire_turns):
            candidate = turn[3][0][0]
            if candidate[1] is None:
                # Blocked / interrupted / deleted responses come back with a
                # short (~29-slot) candidate whose text is None. Skip with a
                # warning — anything unrecognised past this point still crashes.
                logger.warning(f"Skipping incomplete round in {summary['cid']} (no candidate text)")
                continue

            seconds, nanos = turn[4]
            ts = _ts_to_iso_dt(seconds, nanos)
            user_text = turn[2][0][0]
            rcid = candidate[0]
            model_text = candidate[1][0]
            language = candidate[9]
            # Presence-gated: candidate slot 37 (thoughts) and turn slot 9 (gem)
            # are optional. Once present, trust the shape — mis-shape crashes.
            thoughts = candidate[37][0][0] if len(candidate) > 37 and candidate[37] else None
            if len(turn) > 9 and turn[9]:
                gem_name = turn[9][0]

            events.append(
                Message(
                    sender=Role.USER,
                    content=user_text,
                    created=ts,
                    metadata={"rid": turn[0][1]},
                )
            )
            model_meta: dict = {"rcid": rcid, "language": language}
            if thoughts:
                model_meta["thoughts"] = thoughts
            events.append(
                Message(
                    sender=Role.ASSISTANT,
                    content=model_text,
                    created=ts,
                    metadata=model_meta,
                )
            )
    else:
        logger.warning(f"Empty response for {summary['cid']}; recording chat with no turns.")

    created = events[0].created if events else _parse_iso(summary["updated_at"])

    metadata: dict = {
        "uuid": summary["cid"],
        "updated_at": summary["updated_at"],
        "is_pinned": summary["is_pinned"],
    }
    if gem_name:
        metadata["gem"] = gem_name

    return EventLog(
        source="gemini",
        title=summary["title"],
        created=created,
        events=events,
        metadata=metadata,
    )


def _extract_rpc_body(response_text: str, rpcid: str) -> list | None:
    """Pull the wrb.fr entry for `rpcid` out of a batchexecute response and
    parse its inner JSON body. Returns None if the entry has a null body
    (per-item access glitch). Raises if the entry is missing entirely."""
    if not response_text.startswith(BATCH_PREAMBLE):
        raise RuntimeError(f"Unexpected batchexecute preamble: {response_text[:20]!r}")
    rest = response_text[len(BATCH_PREAMBLE) :]
    decoder = json.JSONDecoder()
    i = 0
    while i < len(rest):
        while i < len(rest) and rest[i] != "[":
            i += 1
        if i >= len(rest):
            break
        obj, end = decoder.raw_decode(rest, i)
        i = end
        for entry in obj:
            if isinstance(entry, list) and entry[0] == "wrb.fr" and entry[1] == rpcid:
                if entry[2] is None:
                    return None
                return json.loads(entry[2])
    raise RuntimeError(f"No wrb.fr entry for {rpcid} in batchexecute response.")


def _ts_to_iso(seconds: int, nanos: int) -> str:
    """Google timestamps come as [seconds, nanoseconds] pairs. Emit ISO 8601
    with microsecond precision (nanos truncated to micros)."""
    return _ts_to_iso_dt(seconds, nanos).isoformat().replace("+00:00", "Z")


def _ts_to_iso_dt(seconds: int, nanos: int) -> datetime:
    micros = nanos // 1000
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=micros)


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)
