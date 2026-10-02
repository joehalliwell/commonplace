"""Fetch claude.ai's file-based memory ("Melange") using the browser session cookie."""

from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from commonplace._fetch._base import BaseFetcher
from commonplace._fetch._claude import _provenance
from commonplace._logging import logger
from commonplace._progress import track


class ClaudeMemoryFetcher(BaseFetcher):
    """Records one complete listing plus a read per changed path; endpoints are unofficial, so expect drift."""

    source = "claude-memory"
    cookie_domain = "claude.ai"
    service_name = "Claude"
    login_url = "https://claude.ai"
    extra_headers: ClassVar[dict[str, str]] = {"Accept": "application/json", "Referer": "https://claude.ai/"}

    _org_uuid: str

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        cookies = self._read_cookies()
        org_uuid = cookies.get("lastActiveOrg")
        if not cookies.get("sessionKey"):
            logger.error("No Claude session cookie found. Log in at https://claude.ai in Chrome first.")
            return None
        if not org_uuid:
            logger.error("No lastActiveOrg cookie. Visit https://claude.ai in Chrome to set it.")
            return None

        self._org_uuid = org_uuid

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
