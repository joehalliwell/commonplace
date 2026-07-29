"""Fetch conversations directly from claude.ai using the browser session cookie.

Writes the raw API responses (list + N conversation details) as a gzipped
JSONL file. The paired importer walks that log and produces EventLogs; the
fetcher performs no content-shape fabrication of its own."""

import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from commonplace._fetch._helpers import raise_on_session_error, read_chrome_cookies, request_with_retry
from commonplace._logging import logger
from commonplace._progress import track

# Full Chrome UA is required to pass Cloudflare's bot check.
CLAUDE_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class ClaudeFetcher:
    """Fetch Claude conversations via claude.ai's internal API.

    Endpoints are unofficial; expect drift.

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
    ):
        self._injected_cookies = cookies
        self._transport = transport

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
                "User-Agent": CLAUDE_UA,
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
        data = r.json()
        self._wire_log.append({"endpoint": "conversations", "response": data})
        return data

    def _fetch_detail(self, convo_uuid: str) -> None:
        r = self._get(
            f"https://claude.ai/api/organizations/{self._org_uuid}/chat_conversations/{convo_uuid}",
            params={"tree": "True", "rendering_mode": "raw"},
        )
        self._wire_log.append({"endpoint": "conversation", "cid": convo_uuid, "response": r.json()})

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        r = request_with_retry(self._client, "GET", url, **kwargs)
        raise_on_session_error(r, service_name="Claude", login_url="https://claude.ai")
        return r

    def _write_archive(self, destination: Path) -> Path:
        """Write the raw API responses, gzipped. This is the canonical
        artifact: what Anthropic actually sent. Content-shape wrapping happens
        in the importer, not here."""
        archive = destination / "claude-wire.jsonl.gz"
        with gzip.open(archive, "wt", encoding="utf-8") as f:
            for entry in self._wire_log:
                f.write(json.dumps(entry, ensure_ascii=False))
                f.write("\n")
        return archive
