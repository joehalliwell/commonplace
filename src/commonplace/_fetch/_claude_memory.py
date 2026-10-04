"""Fetch claude.ai's file-based memory ("Melange") using the browser session cookie."""

from datetime import datetime
from pathlib import Path
from typing import Any

from commonplace._fetch._claude import ClaudeSessionFetcher, updated_after


class ClaudeMemoryFetcher(ClaudeSessionFetcher):
    """Records one complete listing plus a read per changed path; the API is strict, so bodies carry nothing extra."""

    source = "claude-memory"

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        with self._signed_in() as client:
            if client is None:
                return None
            fresh = self._list_fresh(since)
            self._read_fresh(fresh, since, self._read)

        # Archived even with nothing fresh: the listing alone is how a deletion is seen.
        return self._write_archive(destination)

    def _list_fresh(self, since: datetime | None) -> list[dict[str, Any]]:
        return updated_after(self._api("POST", "melange/list", endpoint="list", json={}).json()["data"], since)

    def _read(self, item: dict[str, Any]) -> None:
        key = {"path": item["path"]}
        self._api("POST", "melange/read", endpoint="read", key=key, json=key)
