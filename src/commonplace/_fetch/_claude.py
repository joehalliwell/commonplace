"""Fetch conversations directly from claude.ai using the browser session cookie."""

from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from commonplace._fetch._base import BaseFetcher
from commonplace._logging import logger
from commonplace._progress import track


class ClaudeFetcher(BaseFetcher):
    """Records one list call plus N conversation details from claude.ai's
    internal API. Endpoints are unofficial; expect drift."""

    source = "claude"
    cookie_domain = "claude.ai"
    service_name = "Claude"
    login_url = "https://claude.ai"
    extra_headers: ClassVar[dict[str, str]] = {"Accept": "application/json", "Referer": "https://claude.ai/"}

    _org_uuid: str

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        cookies = self._read_cookies()
        session_key = cookies.get("sessionKey")
        org_uuid = cookies.get("lastActiveOrg")
        if not session_key:
            logger.error("No Claude session cookie found. Log in at https://claude.ai in Chrome first.")
            return None
        if not org_uuid:
            logger.error("No lastActiveOrg cookie. Visit https://claude.ai in Chrome to set it.")
            return None

        self._org_uuid = org_uuid

        with self._session(cookies):
            summaries = self._list_conversations()
            fresh = [c for c in summaries if since is None or datetime.fromisoformat(c["updated_at"]) > since]
            logger.info(f"{len(fresh)}/{len(summaries)} conversations new since {since or 'beginning'}")

            if not fresh:
                return None

            for c in track(fresh, "Fetching conversations"):
                self._fetch_detail(c["uuid"])

        return self._write_archive(destination)

    def _list_conversations(self) -> list[dict[str, Any]]:
        r = self._get(f"https://claude.ai/api/organizations/{self._org_uuid}/chat_conversations")
        self._log(endpoint="conversations", response=r.text)
        return r.json()

    def _fetch_detail(self, convo_uuid: str) -> None:
        r = self._get(
            f"https://claude.ai/api/organizations/{self._org_uuid}/chat_conversations/{convo_uuid}",
            params={"tree": "True", "rendering_mode": "raw"},
        )
        self._log(endpoint="conversation", cid=convo_uuid, response=r.text)
