"""Fetch conversations directly from claude.ai using the browser session cookie."""

from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from commonplace._config import DEFAULT_UA
from commonplace._fetch._helpers import raise_on_session_error, read_chrome_cookies, request_with_retry
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._wire import write_archive


class ClaudeFetcher:
    """Records one list call plus N conversation details from claude.ai's
    internal API. Endpoints are unofficial; expect drift.

    Cookies and HTTP transport are injectable — real use passes neither and the
    fetcher discovers cookies from Chrome and uses the real network. Tests
    inject fakes for both."""

    source: str = "claude"

    _client: httpx.Client
    _org_uuid: str
    _wire_log: list[dict[str, Any]]

    def __init__(
        self,
        *,
        cookies: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        ua: str = DEFAULT_UA,
    ):
        self._injected_cookies = cookies
        self._transport = transport
        self._ua = ua

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        cookies = self._injected_cookies if self._injected_cookies is not None else read_chrome_cookies("claude.ai")
        session_key = cookies.get("sessionKey")
        org_uuid = cookies.get("lastActiveOrg")
        if not session_key:
            logger.error("No Claude session cookie found. Log in at https://claude.ai in Chrome first.")
            return None
        if not org_uuid:
            logger.error("No lastActiveOrg cookie. Visit https://claude.ai in Chrome to set it.")
            return None

        self._org_uuid = org_uuid
        self._wire_log = []

        with httpx.Client(
            cookies=cookies,
            headers={
                "User-Agent": self._ua,
                "Accept": "application/json",
                "Referer": "https://claude.ai/",
            },
            timeout=30.0,
            transport=self._transport,
        ) as self._client:
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
        self._wire_log.append({"endpoint": "conversations", "response": r.text})
        return r.json()

    def _fetch_detail(self, convo_uuid: str) -> None:
        r = self._get(
            f"https://claude.ai/api/organizations/{self._org_uuid}/chat_conversations/{convo_uuid}",
            params={"tree": "True", "rendering_mode": "raw"},
        )
        self._wire_log.append({"endpoint": "conversation", "cid": convo_uuid, "response": r.text})

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        r = request_with_retry(self._client, "GET", url, **kwargs)
        raise_on_session_error(r, service_name="Claude", login_url="https://claude.ai")
        return r

    def _write_archive(self, destination: Path) -> Path:
        return write_archive(destination / "claude-wire.jsonl.gz", self.source, self._wire_log)
