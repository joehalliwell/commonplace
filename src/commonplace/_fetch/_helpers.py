"""Shared helpers for Fetcher implementations."""

import os
import time
from pathlib import Path
from typing import Any

import browser_cookie3  # type: ignore[import-untyped]
import httpx

from commonplace._logging import logger

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


def raise_on_session_error(response: httpx.Response, service_name: str, login_url: str) -> None:
    """Raise a uniform RuntimeError on 401/403 (session expired or rejected),
    otherwise `raise_for_status` on any other non-success. Every fetcher
    should call this on responses that aren't already handled by
    `request_with_retry` (which only handles transient statuses)."""
    if response.status_code in (401, 403):
        raise RuntimeError(f"{service_name} session rejected. Log in at {login_url} in Chrome, then retry.")
    response.raise_for_status()
