"""Fetch conversations directly from claude.ai using the browser session cookie."""

import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import httpx

from commonplace._fetch._helpers import last_import_time, read_chrome_cookies, request_with_retry
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace

# Full Chrome UA is required to pass Cloudflare's bot check.
CLAUDE_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class ClaudeFetcher:
    """Fetch Claude conversations via claude.ai's internal API.

    Endpoints are unofficial; expect drift.
    """

    source: str = "claude"

    _client: httpx.Client
    _org_uuid: str

    def fetch(self, destination: Path, repo: Commonplace) -> Path | None:
        cookies = read_chrome_cookies("claude.ai")
        session_key = cookies.get("sessionKey")
        org_uuid = cookies.get("lastActiveOrg")
        if not session_key:
            logger.error("No Claude session cookie found. Log in at https://claude.ai in Chrome first.")
            return None
        if not org_uuid:
            logger.error("No lastActiveOrg cookie. Visit https://claude.ai in Chrome to set it.")
            return None

        since = last_import_time(repo, self.source)
        self._org_uuid = org_uuid

        with httpx.Client(
            cookies=cookies,
            headers={
                "User-Agent": CLAUDE_UA,
                "Accept": "application/json",
                "Referer": "https://claude.ai/",
            },
            timeout=30.0,
        ) as self._client:
            summaries = self._list_conversations()
            fresh = [c for c in summaries if since is None or c["updated_at"] > since]
            logger.info(f"{len(fresh)}/{len(summaries)} conversations new since {since or 'beginning'}")

            if not fresh:
                return None

            conversations = [self._fetch_detail(c["uuid"]) for c in track(fresh, "Fetching conversations")]

        return self._write_archive(conversations, destination)

    def _list_conversations(self) -> list[dict[str, Any]]:
        r = self._get(f"https://claude.ai/api/organizations/{self._org_uuid}/chat_conversations")
        return r.json()

    def _fetch_detail(self, convo_uuid: str) -> dict[str, Any]:
        r = self._get(
            f"https://claude.ai/api/organizations/{self._org_uuid}/chat_conversations/{convo_uuid}",
            params={"tree": "True", "rendering_mode": "raw"},
        )
        return self._to_export_shape(r.json())

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        r = request_with_retry(self._client, "GET", url, **kwargs)
        self._check(r)
        return r

    @staticmethod
    def _to_export_shape(convo: dict[str, Any]) -> dict[str, Any]:
        """The API gives each message a flat `text`; the export ZIP wraps it in
        a `content` block list. Wrap so ClaudeImporter sees a familiar shape."""
        for msg in convo.get("chat_messages", []):
            if not msg.get("content"):
                msg["content"] = [{"type": "text", "text": msg.get("text", "")}]
        return convo

    @staticmethod
    def _write_archive(conversations: list[dict[str, Any]], destination: Path) -> Path:
        archive = destination / "claude-fetch.zip"
        with ZipFile(archive, "w") as zf:
            zf.writestr("conversations.json", json.dumps(conversations))
            zf.writestr("users.json", "[]")
        return archive

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code == 401:
            raise RuntimeError("Claude session expired. Log in at https://claude.ai in Chrome, then retry.")
        r.raise_for_status()
