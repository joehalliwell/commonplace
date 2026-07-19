"""Fetch conversations directly from claude.ai using the browser session cookie."""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import browser_cookie3  # type: ignore[import-untyped]
import httpx

from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace

# Full Chrome UA is required to pass Cloudflare's bot check.
CLAUDE_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Flatpak Chrome stashes its config outside XDG_CONFIG_HOME.
FLATPAK_CHROME_CONFIG = Path.home() / ".var" / "app" / "com.google.Chrome" / "config"

# Retry transient failures (rate-limit / server errors) with exponential backoff.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
BACKOFF_BASE = 1.5


class ClaudeFetcher:
    """Fetch Claude conversations via claude.ai's internal API.

    Endpoints are unofficial; expect drift.
    """

    source: str = "claude"

    def fetch(self, destination: Path, repo: Commonplace) -> Path | None:
        cookies = self._read_cookies()
        session_key = cookies.get("sessionKey")
        org_uuid = cookies.get("lastActiveOrg")
        if not session_key:
            logger.error("No Claude session cookie found. Log in at https://claude.ai in Chrome first.")
            return None
        if not org_uuid:
            logger.error("No lastActiveOrg cookie. Visit https://claude.ai in Chrome to set it.")
            return None

        since = _last_import_time(repo, f"chats/{self.source}/")

        with httpx.Client(
            cookies=cookies,
            headers={
                "User-Agent": CLAUDE_UA,
                "Accept": "application/json",
                "Referer": "https://claude.ai/",
            },
            timeout=30.0,
        ) as client:
            summaries = _list_conversations(client, org_uuid)
            fresh = [c for c in summaries if since is None or c["updated_at"] > since]
            logger.info(f"{len(fresh)}/{len(summaries)} conversations new since {since or 'beginning'}")

            if not fresh:
                return None

            conversations = [_fetch_detail(client, org_uuid, c["uuid"]) for c in track(fresh, "Fetching conversations")]

        return _write_archive(conversations, destination)

    def _read_cookies(self) -> dict[str, str]:
        if FLATPAK_CHROME_CONFIG.exists():
            os.environ["XDG_CONFIG_HOME"] = str(FLATPAK_CHROME_CONFIG)
        jar = browser_cookie3.chrome(domain_name="claude.ai")
        return {c.name: c.value for c in jar if c.value}


def _last_import_time(repo: Commonplace, pathspec: str) -> str | None:
    """ISO timestamp of the most recent commit touching pathspec, or None if
    the path has no history yet. Beware: this is the commit time, which is
    always ≥ max(updated_at) of the last-imported convos, so a conversation
    edited on claude.ai *during* a fetch may be missed until it changes again."""
    result = subprocess.run(
        ["git", "-C", str(repo.root), "log", "-1", "--format=%aI", "--", pathspec],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None


def _list_conversations(client: httpx.Client, org_uuid: str) -> list[dict[str, Any]]:
    r = _get_with_retry(client, f"https://claude.ai/api/organizations/{org_uuid}/chat_conversations")
    return r.json()


def _fetch_detail(client: httpx.Client, org_uuid: str, convo_uuid: str) -> dict[str, Any]:
    r = _get_with_retry(
        client,
        f"https://claude.ai/api/organizations/{org_uuid}/chat_conversations/{convo_uuid}",
        params={"tree": "True", "rendering_mode": "raw"},
    )
    return _to_export_shape(r.json())


def _get_with_retry(client: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
    for attempt in range(MAX_RETRIES):
        r = client.get(url, **kwargs)
        if r.status_code not in RETRY_STATUSES:
            _check(r)
            return r
        delay = BACKOFF_BASE**attempt
        logger.warning(f"Got {r.status_code} from {url}; retrying in {delay:.1f}s")
        time.sleep(delay)
    _check(r)
    return r


def _to_export_shape(convo: dict[str, Any]) -> dict[str, Any]:
    """The API gives each message a flat `text`; the export ZIP wraps it in a
    `content` block list. Wrap so ClaudeImporter sees a familiar shape."""
    for msg in convo.get("chat_messages", []):
        if not msg.get("content"):
            msg["content"] = [{"type": "text", "text": msg.get("text", "")}]
    return convo


def _write_archive(conversations: list[dict[str, Any]], destination: Path) -> Path:
    archive = destination / "claude-fetch.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("conversations.json", json.dumps(conversations))
        zf.writestr("users.json", "[]")
    return archive


def _check(r: httpx.Response) -> None:
    if r.status_code == 401:
        raise RuntimeError("Claude session expired. Log in at https://claude.ai in Chrome, then retry.")
    r.raise_for_status()
