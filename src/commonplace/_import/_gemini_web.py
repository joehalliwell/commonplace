"""Importer for the JSON produced by [[GeminiFetcher]].

Deliberately fail-loud: if the fetcher's output shape drifts, we want a
KeyError, not silent field loss.
"""

import json
from datetime import datetime
from pathlib import Path

from commonplace._import._types import EventLog, Message, Role


class GeminiWebImporter:
    """Consumes gemini-fetch.json emitted by the fetcher."""

    source: str = "gemini"

    def required_paths(self) -> list[str]:
        return []

    def can_import(self, path: Path) -> bool:
        if path.suffix != ".json":
            return False
        # Fetcher output is a top-level array whose first object has `cid`.
        head = path.read_bytes()[:2048].lstrip()
        return head.startswith(b"[{") and b'"cid"' in head

    def import_(self, path: Path) -> list[EventLog]:
        data = json.loads(path.read_text())
        return [self._to_log(chat) for chat in data]

    def _to_log(self, chat: dict) -> EventLog:
        events: list[Message] = []
        for round_ in chat["rounds"]:
            ts = _parse_iso(round_["timestamp"])
            events.append(
                Message(
                    sender=Role.USER,
                    content=round_["user_text"],
                    created=ts,
                    metadata={"rid": round_["rid"]},
                )
            )
            model_meta: dict = {"rcid": round_["rcid"], "language": round_["language"]}
            if round_["model_thoughts"]:
                model_meta["thoughts"] = round_["model_thoughts"]
            events.append(
                Message(
                    sender=Role.ASSISTANT,
                    content=round_["model_text"],
                    created=ts,
                    metadata=model_meta,
                )
            )

        # Rounds are in chronological order; created = first, updated_at from wire.
        created = _parse_iso(chat["rounds"][0]["timestamp"]) if chat["rounds"] else _parse_iso(chat["updated_at"])

        metadata: dict = {
            "uuid": chat["cid"],
            "updated_at": chat["updated_at"],
            "is_pinned": chat["is_pinned"],
        }
        if chat["gem_name"]:
            metadata["gem"] = chat["gem_name"]

        return EventLog(
            source=self.source,
            title=chat["title"],
            created=created,
            events=events,
            metadata=metadata,
        )


def _parse_iso(s: str) -> datetime:
    """Fetcher emits ISO 8601 with a trailing Z; datetime.fromisoformat wants
    an explicit offset."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)
