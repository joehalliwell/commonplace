"""Fetch claude.ai's file-based memory ("Melange") using the browser session cookie."""

from datetime import datetime
from pathlib import Path
from typing import Any

from commonplace._fetch._claude import ClaudeSessionFetcher, _provenance
from commonplace._logging import logger
from commonplace._progress import track


class ClaudeMemoryFetcher(ClaudeSessionFetcher):
    """Records one complete listing plus a read per changed path; endpoints are unofficial, so expect drift."""

    source = "claude-memory"

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        cookies = self._authenticate()
        if cookies is None:
            return None

        with self._session(cookies):
            listing = self._post("list", {})["data"]
            fresh = [m for m in listing if since is None or datetime.fromisoformat(m["updated_at"]) > since]
            logger.info(f"{len(fresh)}/{len(listing)} memories new since {since or 'beginning'}")

            for m in track(fresh, "Fetching memories"):
                self._post("read", {"path": m["path"]})

        # Written even with nothing fresh: the listing alone is how a deletion is seen.
        return self._write_archive(destination)

    def _post(self, endpoint: str, body: dict[str, str]) -> Any:
        """POST to a melange endpoint and log the response; the API is strict, so `body` carries nothing extra."""
        r = self._request("POST", f"https://claude.ai/api/organizations/{self._org_uuid}/melange/{endpoint}", json=body)
        self._log(endpoint=endpoint, **body, **_provenance(r), response=r.text)
        return r.json()
