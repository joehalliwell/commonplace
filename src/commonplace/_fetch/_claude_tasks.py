"""Fetch the runs of claude.ai scheduled tasks: Code sessions until 2026-11-13, claude.ai chats since."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from commonplace._fetch._claude import ClaudeSessionFetcher, updated_after


class ClaudeTasksFetcher(ClaudeSessionFetcher):
    """Records both run listings in full, plus everything said in each run active since the cursor."""

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        with self._signed_in():
            sessions = self._fresh_sessions(since)
            self._read_fresh(sessions, since, self._read_session)
            chats = self._fresh_chats(since)
            self._read_fresh(chats, since, self._read_chat)

        return [self._write_archive(destination)] if sessions or chats else []

    def _fresh_sessions(self, since: datetime | None) -> list[dict[str, Any]]:
        """Runs that were Code sessions, active since `since`."""
        # The server returns no runs at all without `exclude_tags`.
        runs = self._code_pages(
            "sessions", endpoint="sessions", only_trigger_sessions="true", limit="200", exclude_tags="-"
        )
        # `last_event_at`, not `updated_at`: a follow-up in the run's chat is new content; reading it is not.
        return [r for r in runs if since is None or datetime.fromisoformat(r["last_event_at"]) > since]

    def _read_session(self, run: dict[str, Any]) -> None:
        self._code_pages(f"sessions/{run['id']}/events", endpoint="events", key={"sid": run["id"]})

    def _fresh_chats(self, since: datetime | None) -> list[dict[str, Any]]:
        """Runs that are chats, updated since `since`; the default chat listing leaves them out."""
        chats = self._api("GET", "chat_conversations", endpoint="conversations", params={"platforms": "ROUTINE_RUN"})
        return updated_after(chats.json(), since)

    def _read_chat(self, chat: dict[str, Any]) -> None:
        # `raw` rendering replaces each tool call with a placeholder.
        self._api(
            "GET",
            f"chat_conversations/{chat['uuid']}",
            endpoint="conversation",
            key={"cid": chat["uuid"]},
            params={"tree": "True", "rendering_mode": "messages", "render_all_tools": "true"},
        )
