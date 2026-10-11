"""Fetch the runs of claude.ai scheduled tasks, which are Code sessions rather than chats."""

from datetime import datetime
from pathlib import Path
from typing import Any

from commonplace._fetch._claude import ClaudeSessionFetcher


class ClaudeTasksFetcher(ClaudeSessionFetcher):
    """Records the complete run listing plus every page of events for each run active since the cursor."""

    source = "claude-tasks"

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        with self._signed_in() as client:
            if client is None:
                return None
            # The server returns no runs at all without `exclude_tags`.
            runs = self._code_pages(
                "sessions", endpoint="sessions", only_trigger_sessions="true", limit="200", exclude_tags="-"
            )
            # `last_event_at`, not `updated_at`: a follow-up in the run's chat is new content; reading it is not.
            fresh = [r for r in runs if since is None or datetime.fromisoformat(r["last_event_at"]) > since]
            self._read_fresh(fresh, since, self._read)

        return self._write_archive(destination) if fresh else None

    def _read(self, run: dict[str, Any]) -> None:
        self._code_pages(f"sessions/{run['id']}/events", endpoint="events", key={"sid": run["id"]})
