"""Fetch ChatGPT's memory of the user from chatgpt.com using the browser session cookie."""

from datetime import datetime
from pathlib import Path

from commonplace._fetch._chatgpt import ChatGptFetcher

MEMORIES_URL = "https://chatgpt.com/backend-api/memories"
SUMMARY_URL = "https://chatgpt.com/backend-api/memories/about_you/summary/stream"


class ChatGptMemoryFetcher(ChatGptFetcher):
    """Records the saved-memories list and the streamed about-you summary, whole, on every run."""

    source = "chatgpt-memory"

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        # Neither endpoint can be asked for changes only, so `since` has nothing to narrow.
        with self._signed_in() as client:
            if client is None:
                return None
            self._log(endpoint="memories", response=self._get(MEMORIES_URL).text)
            self._log(endpoint="summary", response=self._request("POST", SUMMARY_URL, json={}).text)

        return self._write_archive(destination)
