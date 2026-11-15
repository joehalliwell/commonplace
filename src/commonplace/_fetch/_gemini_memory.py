"""Fetch Gemini's saved info (gemini.google.com/saved-info) over the same `batchexecute` RPC as chats."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from commonplace._fetch._gemini import GeminiSessionFetcher
from commonplace._import._gemini_memory import RPC_LIST_SAVED_INFO
from commonplace._progress import track


class GeminiMemoryFetcher(GeminiSessionFetcher):
    """Records the one call that returns every saved item; there is nothing per item to read."""

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        # `since` goes unused: the listing is the whole state, and it is how a deletion is seen.
        with self._signed_in():
            for path in track(["/saved-info"], f"Fetching {self.source.name}"):
                self._rpc_body(RPC_LIST_SAVED_INFO, [], source_path=path)

        return [self._write_archive(destination)]
