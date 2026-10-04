"""Fetch ChatGPT's memory of the user from chatgpt.com using the browser session cookie."""

from datetime import datetime
from pathlib import Path

from commonplace._fetch._chatgpt import ChatGptSessionFetcher


class ChatGptMemoryFetcher(ChatGptSessionFetcher):
    """Records the saved-memories list and the streamed about-you summary, whole, on every run."""

    source = "chatgpt-memory"

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        # Neither endpoint can be asked for changes only, so `since` has nothing to narrow.
        with self._signed_in() as client:
            if client is None:
                return None
            self._api("GET", "memories", endpoint="memories")
            self._api("POST", "memories/about_you/summary/stream", endpoint="summary", json={})

        return self._write_archive(destination)
