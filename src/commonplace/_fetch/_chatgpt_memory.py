"""Fetch ChatGPT's memory of the user from chatgpt.com using the browser session cookie."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import httpx

from commonplace._fetch._base import CONNECT_TIMEOUT
from commonplace._fetch._chatgpt import ChatGptSessionFetcher
from commonplace._progress import track

#: The summary regenerates on request, and can go quiet while it does: 56 s end to end on 2026-11-01.
SUMMARY_READ_TIMEOUT = 180.0


class ChatGptMemoryFetcher(ChatGptSessionFetcher):
    """Records the saved-memories list and the streamed about-you summary, whole, on every run."""

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        # Neither endpoint can be asked for changes only, so `since` has nothing to narrow.
        with self._signed_in():
            for endpoint in track(["memories", "summary"], f"Fetching {self.source.name}"):
                self._call(endpoint)

        return [self._write_archive(destination)]

    def _call(self, endpoint: str) -> None:
        """Record one of the two endpoints: the saved memories, or the summary, which can take minutes."""
        if endpoint == "memories":
            self._api("GET", "memories", endpoint="memories")
            return
        timeout = httpx.Timeout(SUMMARY_READ_TIMEOUT, connect=CONNECT_TIMEOUT)
        self._api("POST", "memories/about_you/summary/stream", endpoint="summary", json={}, timeout=timeout)
