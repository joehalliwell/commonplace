"""Fetch Gemini's saved info (gemini.google.com/saved-info) over the same `batchexecute` RPC as chats."""

from datetime import datetime
from pathlib import Path

from commonplace._fetch._gemini import GeminiSessionFetcher
from commonplace._import._gemini_memory import RPC_LIST_SAVED_INFO


class GeminiMemoryFetcher(GeminiSessionFetcher):
    """Records the one call that returns every saved item; there is nothing per item to read."""

    source = "gemini-memory"

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        # `since` goes unused: the listing is the whole state, and it is how a deletion is seen.
        with self._signed_in() as client:
            if client is None:
                return None
            if self._call_rpc(RPC_LIST_SAVED_INFO, [], source_path="/saved-info") is None:
                raise RuntimeError(f"{RPC_LIST_SAVED_INFO} returned a null wrb.fr body — protocol may have changed.")

        return self._write_archive(destination)
