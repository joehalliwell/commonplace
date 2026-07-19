"""Fetch conversations directly from gemini.google.com.

Reverse-engineered against the internal `batchexecute` RPC. Endpoints and
slot indices are unofficial and can change without notice — this module is
deliberately fail-loud (no `.get()` defaults on wire fields) so drift
surfaces immediately rather than as silent data loss.
"""

import gzip
import json
import os
import random
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import browser_cookie3  # type: ignore[import-untyped]
import httpx

from commonplace._import._gemini import _extract_rpc_body, _ts_to_iso
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace

CHROME_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
FLATPAK_CHROME_CONFIG = Path.home() / ".var" / "app" / "com.google.Chrome" / "config"

INIT_URL = "https://gemini.google.com/app"
BATCH_URL = "https://gemini.google.com/_/BardChatUi/data/batchexecute"

RPC_LIST_CHATS = "MaZiqc"
RPC_READ_CHAT = "hNvQHb"

# Retry transient failures with exponential backoff.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
BACKOFF_BASE = 1.5


class GeminiFetcher:
    """Fetch Gemini conversations via gemini.google.com's `batchexecute` RPC."""

    source: str = "gemini"

    _client: httpx.Client
    _access_token: str
    _build_label: str
    _session_id: str
    _wire_log: list[dict[str, Any]]

    def fetch(self, destination: Path, repo: Commonplace) -> Path | None:
        cookies = self._read_cookies()
        if not cookies.get("__Secure-1PSID"):
            logger.error("No Gemini session cookie found. Log in at https://gemini.google.com in Chrome first.")
            return None

        since = self._last_import_time(repo)
        self._wire_log = []

        with httpx.Client(
            cookies=cookies,
            headers={
                "User-Agent": CHROME_UA,
                "Origin": "https://gemini.google.com",
                "Referer": "https://gemini.google.com/",
                "X-Same-Domain": "1",
                "x-goog-ext-525001261-jspb": "[1,null,null,null,null,null,null,null,[4]]",
                "x-goog-ext-73010989-jspb": "[0]",
            },
            follow_redirects=True,
            timeout=60.0,
        ) as self._client:
            self._read_session_tokens()

            # Walk list_chats pages to find fresh cids. Full parse of each chat
            # happens in the importer against the same wire we're logging here.
            fresh_cids = list(self._list_fresh_cids(since))
            logger.info(f"{len(fresh_cids)} conversations new since {since or 'beginning'}")

            if not fresh_cids:
                return None

            for cid in track(fresh_cids, "Fetching conversations"):
                self._call_rpc(RPC_READ_CHAT, [cid, 1000, None, 1, [1], [4], None, 1])

        return self._write_archive(destination)

    def _read_cookies(self) -> dict[str, str]:
        if FLATPAK_CHROME_CONFIG.exists():
            os.environ["XDG_CONFIG_HOME"] = str(FLATPAK_CHROME_CONFIG)
        jar = browser_cookie3.chrome(domain_name=".google.com")
        return {c.name: c.value for c in jar if c.value}

    def _last_import_time(self, repo: Commonplace) -> str | None:
        """ISO timestamp of the most recent commit touching this source's
        chats, or None if none. Same commit-time cursor caveat as
        [[claude fetcher]]."""
        result = subprocess.run(
            ["git", "-C", str(repo.root), "log", "-1", "--format=%aI", "--", f"chats/{self.source}/"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() or None

    def _read_session_tokens(self) -> None:
        """Scrape SNlM0e (access token), cfb2h (build label), and FdrFJe
        (session id) from the /app page HTML."""
        r = self._client.get(INIT_URL)
        r.raise_for_status()
        self._access_token = _require_match(r.text, r'"SNlM0e":"([^"]+)"', "access token (SNlM0e)")
        self._build_label = _require_match(r.text, r'"cfb2h":"([^"]+)"', "build label (cfb2h)")
        self._session_id = _require_match(r.text, r'"FdrFJe":"(-?\d+)"', "session id (FdrFJe)")

    def _list_fresh_cids(self, since: str | None):
        """Walk both pinned + unpinned buckets. Yield cids whose updated_at is
        newer than `since`. All list_chats responses are still logged verbatim
        to wire.jsonl (the importer re-parses them for title / is_pinned)."""
        for pinned in (1, 0):
            cursor: str | None = None
            while True:
                body = self._call_rpc(RPC_LIST_CHATS, [100, cursor, [pinned, None, 1]])
                # A null body from list_chats would be a real protocol issue
                # (unlike read_chat, where it signals a per-item glitch).
                if body is None:
                    raise RuntimeError("list_chats returned a null wrb.fr body — protocol may have changed.")
                cursor = body[1]
                rows = body[2]
                for row in rows:
                    seconds, nanos = row[5]
                    updated_at = _ts_to_iso(seconds, nanos)
                    if since is None or updated_at > since:
                        yield row[0]
                if not cursor or not rows:
                    break

    def _call_rpc(self, rpcid: str, payload: list) -> list | None:
        """Wrap payload in the batchexecute envelope, POST, parse, return the
        RPC response body (parsed from the wrb.fr[2] string). Returns None if
        the wrb.fr entry has a null body (Gemini's way of signalling a per-item
        access glitch). A missing wrb.fr entry entirely still raises.

        The raw response is appended to `self._wire_log` so it can be preserved
        as provenance alongside the parsed output."""
        params = {
            "rpcids": rpcid,
            "_reqid": random.randint(10000, 99999),
            "rt": "c",
            "source-path": "/app",
            "bl": self._build_label,
            "f.sid": self._session_id,
        }
        envelope = json.dumps([[[rpcid, json.dumps(payload), None, "generic"]]])
        data = {"at": self._access_token, "f.req": envelope}
        headers = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
        r = self._post_with_retry(BATCH_URL, params=params, data=data, headers=headers)
        self._wire_log.append({"rpc": rpcid, "payload": payload, "response": r.text})
        return _extract_rpc_body(r.text, rpcid)

    def _post_with_retry(self, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(MAX_RETRIES):
            r = self._client.post(url, **kwargs)
            if r.status_code not in RETRY_STATUSES:
                self._check(r)
                return r
            delay = BACKOFF_BASE**attempt
            logger.warning(f"Got {r.status_code} from {url}; retrying in {delay:.1f}s")
            time.sleep(delay)
        self._check(r)
        return r

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code == 401 or r.status_code == 403:
            raise RuntimeError("Gemini session rejected. Log in at https://gemini.google.com in Chrome, then retry.")
        r.raise_for_status()

    def _write_archive(self, destination: Path) -> Path:
        """Write the raw `batchexecute` responses, gzipped. This is the
        canonical artifact: what Google actually sent. The importer re-parses
        it into EventLogs; there is no fabricated intermediate format.

        Content is opaque JSON either way, so compressing costs no inspection
        convenience and saves ~7× on disk / LFS bandwidth."""
        archive = destination / "gemini-wire.jsonl.gz"
        with gzip.open(archive, "wt", encoding="utf-8") as f:
            for entry in self._wire_log:
                f.write(json.dumps(entry, ensure_ascii=False))
                f.write("\n")
        return archive


def _require_match(text: str, pattern: str, name: str) -> str:
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError(f"Could not extract {name} from Gemini /app page — HTML shape may have changed.")
    return m.group(1)
