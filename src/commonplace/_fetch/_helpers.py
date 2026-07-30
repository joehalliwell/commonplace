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
    if is_bot_challenge(response):
        raise RuntimeError(
            f"{service_name} served a Cloudflare bot challenge, not a session error — logging in again won't help. "
            f"Open {login_url} in Chrome to clear it, then retry."
        )
    if response.status_code in (401, 403):
        raise RuntimeError(f"{service_name} session rejected. Log in at {login_url} in Chrome, then retry.")
    response.raise_for_status()


def is_bot_challenge(response: httpx.Response) -> bool:
    """Whether a 403 is Cloudflare's bot check rather than the provider's own
    auth rejection.

    Worth distinguishing because the remedies differ: a real session error
    needs a fresh login, whereas a challenge needs the browser to solve it and
    refresh `cf_clearance` — and it clears on its own. The tell is a 403 served
    by Cloudflare with an HTML body; the provider APIs answer in JSON."""
    return (
        response.status_code == 403
        and "cloudflare" in response.headers.get("server", "").lower()
        and "html" in response.headers.get("content-type", "").lower()
    )
