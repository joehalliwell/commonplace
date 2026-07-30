"""Shared helpers for Fetcher implementations."""

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import browser_cookie3  # type: ignore[import-untyped]
import httpx

from commonplace._logging import logger

# Flatpak Chrome stashes its config outside XDG_CONFIG_HOME.
FLATPAK_CHROME_CONFIG = Path.home() / ".var" / "app" / "com.google.Chrome" / "config"

# A full, current Chrome UA — every provider sits behind a bot check that a
# terse or stale one fails. Shared so all three fetchers age together: bump it
# here when Chrome moves on.
CHROME_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Retry transient failures with exponential backoff.
RETRY_STATUSES = {429, 500, 502, 503, 504}
THROTTLE_STATUSES = {429}
MAX_RETRIES = 5
BACKOFF_BASE = 1.5


def read_chrome_cookies(domain: str) -> dict[str, str]:
    """Read cookies for a domain from the logged-in Chrome browser. Handles
    the Flatpak Chrome path automatically."""
    if FLATPAK_CHROME_CONFIG.exists():
        os.environ["XDG_CONFIG_HOME"] = str(FLATPAK_CHROME_CONFIG)
    jar = browser_cookie3.chrome(domain_name=domain)
    return {c.name: c.value for c in jar if c.value}


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    on_throttled: Callable[[], None] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Send an HTTP request; retry on transient (429/5xx) with exponential
    backoff. Callers handle auth-error checking on the returned response —
    retry only covers transient network/server issues.

    `on_throttled` fires when the server answers 429. Retrying alone forgets
    that it happened; a caller pacing itself wants to stay slower afterwards."""
    for attempt in range(MAX_RETRIES):
        r = client.request(method, url, **kwargs)
        if r.status_code not in RETRY_STATUSES:
            return r
        if r.status_code in THROTTLE_STATUSES and on_throttled is not None:
            on_throttled()
        delay = BACKOFF_BASE**attempt
        logger.warning(f"Got {r.status_code} from {url}; retrying in {delay:.1f}s")
        time.sleep(delay)
    return r


class Pacer:
    """Spaces successive requests, widening the gap when a server pushes back.

    Pure backoff would be preferable — pay nothing until told to slow down —
    but Cloudflare-fronted APIs answer a burst with a bot challenge rather than
    a 429, and a challenge cannot be retried away: it invalidates
    `cf_clearance` and needs the browser to solve it. There is no second chance
    to react, so the gap starts non-zero and only widens.

    Call `wait()` before each request and pass `slow_down` as
    `request_with_retry`'s `on_throttled`.
    """

    def __init__(self, interval: float, max_interval: float = 8.0, factor: float = 2.0, first_step: float = 0.25):
        self.interval = interval
        self._max_interval = max_interval
        self._factor = factor
        self._first_step = first_step
        self._last_at: float | None = None

    def wait(self) -> None:
        if self._last_at is not None:
            remaining = self.interval - (time.monotonic() - self._last_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_at = time.monotonic()

    def slow_down(self) -> None:
        """Widen the gap for the rest of the run. Never narrows again — within
        one fetch, evidence that we were too fast doesn't expire.

        Escalates from `first_step` rather than scaling the current interval, so
        a `Pacer(0)` — free until the server objects — can still widen. Scaling
        zero would leave it stuck at zero."""
        widened = min(max(self.interval, self._first_step) * self._factor, self._max_interval)
        if widened > self.interval:
            logger.info(f"Throttled; pacing requests {widened:.1f}s apart")
        self.interval = widened


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
