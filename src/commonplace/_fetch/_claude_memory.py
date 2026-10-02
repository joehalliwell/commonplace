"""Fetch claude.ai's file-based memory ("Melange") using the browser session cookie."""

from typing import Any

from commonplace._fetch._claude import ClaudeSessionFetcher


class ClaudeMemoryFetcher(ClaudeSessionFetcher):
    """Records one complete listing plus a read per changed path; the API is strict, so bodies carry nothing extra."""

    source = "claude-memory"
    noun = "memories"
    #: The listing alone is how a deletion is seen.
    archive_when_unchanged = True

    def _list(self) -> list[dict[str, Any]]:
        return self._api("POST", "melange/list", endpoint="list", json={}).json()["data"]

    def _read(self, item: dict[str, Any]) -> None:
        key = {"path": item["path"]}
        self._api("POST", "melange/read", endpoint="read", key=key, json=key)
