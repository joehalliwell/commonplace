"""Fetch conversations directly from gemini.google.com.

Reverse-engineered against the internal `batchexecute` RPC. Endpoints and
slot indices are unofficial and can change without notice — this module is
deliberately fail-loud (no `.get()` defaults on wire fields) so drift
surfaces immediately rather than as silent data loss.
"""

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

# Google returns chunked size-prefixed JSON blobs after a ")]}'" preamble.
BATCH_PREAMBLE = ")]}'\n"


class GeminiFetcher:
    """Fetch Gemini conversations via gemini.google.com's `batchexecute` RPC."""

    source: str = "gemini"

    _client: httpx.Client
    _access_token: str
    _build_label: str
    _session_id: str

    def fetch(self, destination: Path, repo: Commonplace) -> Path | None:
        cookies = self._read_cookies()
        if not cookies.get("__Secure-1PSID"):
            logger.error("No Gemini session cookie found. Log in at https://gemini.google.com in Chrome first.")
            return None

        since = self._last_import_time(repo)

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

            summaries = list(self._list_all_chats())
            fresh = [c for c in summaries if since is None or c["updated_at"] > since]
            logger.info(f"{len(fresh)}/{len(summaries)} conversations new since {since or 'beginning'}")

            if not fresh:
                return None

            conversations = [self._read_chat(c) for c in track(fresh, "Fetching conversations")]

        return self._write_archive(conversations, destination)

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

    def _list_all_chats(self):
        """Yield chat summaries across both pinned + unpinned buckets, following
        the cursor until exhausted."""
        for pinned in (1, 0):
            cursor: str | None = None
            while True:
                body = self._call_rpc(RPC_LIST_CHATS, [100, cursor, [pinned, None, 1]])
                cursor = body[1]
                rows = body[2]
                for row in rows:
                    seconds, nanos = row[5]
                    yield {
                        "cid": row[0],
                        "title": row[1],
                        "is_pinned": bool(pinned),
                        "updated_at": _ts_to_iso(seconds, nanos),
                    }
                if not cursor or not rows:
                    break

    def _read_chat(self, summary: dict[str, Any]) -> dict[str, Any]:
        body = self._call_rpc(RPC_READ_CHAT, [summary["cid"], 1000, None, 1, [1], [4], None, 1])
        if body is None:
            # Gemini sometimes returns an empty wrb.fr body for individual chats
            # (per-chat access glitches). Emit an empty log and press on.
            logger.warning(f"Empty response for {summary['cid']}; recording chat with no turns.")
            return {**summary, "gem_name": None, "rounds": []}
        wire_turns = body[0]

        rounds = []
        gem_name = None
        # Wire returns newest-first; reverse to chronological.
        for turn in reversed(wire_turns):
            candidate = turn[3][0][0]
            # Blocked / interrupted / deleted responses come back with a short
            # (~29-slot) candidate whose text is None. Skip the round with a
            # warning — anything unrecognised past this point still crashes.
            if candidate[1] is None:
                logger.warning(f"Skipping incomplete round in {summary['cid']} (no candidate text)")
                continue

            seconds, nanos = turn[4]
            ts = _ts_to_iso(seconds, nanos)
            user_text = turn[2][0][0]
            rcid = candidate[0]
            model_text = candidate[1][0]
            language = candidate[9]
            thoughts = None
            if len(candidate) > 37 and isinstance(candidate[37], list) and candidate[37]:
                inner = candidate[37][0]
                if isinstance(inner, list) and inner and isinstance(inner[0], str):
                    thoughts = inner[0]
            # Gem lives at turn[9][0]; absent on non-Gem chats (shorter turn).
            if len(turn) > 9 and turn[9] and isinstance(turn[9][0], str) and turn[9][0]:
                gem_name = turn[9][0]

            rounds.append(
                {
                    "timestamp": ts,
                    "rid": turn[0][1],
                    "rcid": rcid,
                    "user_text": user_text,
                    "model_text": model_text,
                    "model_thoughts": thoughts,
                    "language": language,
                }
            )

        return {
            "cid": summary["cid"],
            "title": summary["title"],
            "is_pinned": summary["is_pinned"],
            "updated_at": summary["updated_at"],
            "gem_name": gem_name,
            "rounds": rounds,
        }

    def _call_rpc(self, rpcid: str, payload: list) -> list | None:
        """Wrap payload in the batchexecute envelope, POST, parse, return the
        RPC response body (parsed from the wrb.fr[2] string). Returns None if
        the wrb.fr entry has a null body (Gemini's way of signalling a per-item
        access glitch). A missing wrb.fr entry entirely still raises."""
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

    @staticmethod
    def _write_archive(conversations: list[dict[str, Any]], destination: Path) -> Path:
        archive = destination / "gemini-fetch.json"
        archive.write_text(json.dumps(conversations, ensure_ascii=False))
        return archive


def _require_match(text: str, pattern: str, name: str) -> str:
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError(f"Could not extract {name} from Gemini /app page — HTML shape may have changed.")
    return m.group(1)


def _ts_to_iso(seconds: int, nanos: int) -> str:
    """Google timestamps come as [seconds, nanoseconds] pairs. Emit ISO 8601
    with microsecond precision (nanos truncated to micros) so timestamps
    sort lexicographically and match the Claude fetcher's format."""
    from datetime import datetime, timezone

    micros = nanos // 1000
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=micros)
    return dt.isoformat().replace("+00:00", "Z")


def _extract_rpc_body(response_text: str, rpcid: str) -> list | None:
    """Pull the wrb.fr entry for `rpcid` out of a batchexecute response and
    parse its inner JSON body. Size prefixes are UTF-16 code units, so we
    use raw_decode to walk chunks instead of trusting the counts.

    Returns None if the wrb.fr entry is present but its body is null (per-item
    access glitch). Raises if the entry is missing entirely (protocol drift)."""
    if not response_text.startswith(BATCH_PREAMBLE):
        raise RuntimeError(f"Unexpected batchexecute preamble: {response_text[:20]!r}")
    rest = response_text[len(BATCH_PREAMBLE) :]
    decoder = json.JSONDecoder()
    i = 0
    while i < len(rest):
        while i < len(rest) and rest[i] != "[":
            i += 1
        if i >= len(rest):
            break
        obj, end = decoder.raw_decode(rest, i)
        i = end
        for entry in obj:
            if isinstance(entry, list) and entry[0] == "wrb.fr" and entry[1] == rpcid:
                if entry[2] is None:
                    return None
                return json.loads(entry[2])
    raise RuntimeError(f"No wrb.fr entry for {rpcid} in batchexecute response.")
