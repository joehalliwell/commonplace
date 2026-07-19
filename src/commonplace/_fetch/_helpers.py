"""Shared helpers for Fetcher implementations."""

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import browser_cookie3  # type: ignore[import-untyped]
import httpx

from commonplace._logging import logger
from commonplace._repo import Commonplace

# Flatpak Chrome stashes its config outside XDG_CONFIG_HOME.
FLATPAK_CHROME_CONFIG = Path.home() / ".var" / "app" / "com.google.Chrome" / "config"

# Retry transient failures with exponential backoff.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
BACKOFF_BASE = 1.5


def read_chrome_cookies(domain: str) -> dict[str, str]:
    """Read cookies for a domain from the logged-in Chrome browser. Handles
    the Flatpak Chrome path automatically."""
    if FLATPAK_CHROME_CONFIG.exists():
        os.environ["XDG_CONFIG_HOME"] = str(FLATPAK_CHROME_CONFIG)
    jar = browser_cookie3.chrome(domain_name=domain)
    return {c.name: c.value for c in jar if c.value}


def last_import_time(repo: Commonplace, source: str) -> str | None:
    """ISO timestamp of the most recent commit touching `chats/{source}/`, or
    None if no such history yet. Beware: this is commit time, always ≥
    max(updated_at) of the last import, so a conversation edited on the remote
    *during* a fetch may be missed until it changes again."""
    result = subprocess.run(
        ["git", "-C", str(repo.root), "log", "-1", "--format=%aI", "--", f"chats/{source}/"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None


def request_with_retry(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Send an HTTP request; retry on transient (429/5xx) with exponential
    backoff. Callers handle auth-error checking on the returned response —
    retry only covers transient network/server issues."""
    for attempt in range(MAX_RETRIES):
        r = client.request(method, url, **kwargs)
        if r.status_code not in RETRY_STATUSES:
            return r
        delay = BACKOFF_BASE**attempt
        logger.warning(f"Got {r.status_code} from {url}; retrying in {delay:.1f}s")
        time.sleep(delay)
    return r
