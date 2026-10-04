"""Shared plumbing for Fetcher implementations.

Every provider needs the same four things: cookies from the logged-in browser,
an HTTP client that passes for that browser, a request path that retries
transient failures and names blocking ones, and a wire archive at the end.
Only the details differ, and they differ by *value* — a domain, a service name,
a few headers — not by shape.

Signing in is the same three steps everywhere — check the session cookie,
open the client, do whatever the API wants before its first real call — so
[[BaseFetcher._signed_in]] runs them, and a provider fills in only the cookie
check and the post-open step. What stays out of this class is `fetch()` itself
and pagination: across providers those differ by shape, and a template method
over them would obscure more than it saved.

Within a provider they do not, so share everything there: the claude.ai
fetchers put the whole walk in [[commonplace._fetch._claude.ClaudeSessionFetcher]].
Sharing costs nothing in robustness. A fetcher is brittle by nature — it tracks
an unofficial upstream and breaks when that moves — so code two fetchers share
is not new coupling, only one place to fix instead of two.

[[commonplace._fetch._types.Fetcher]] remains the contract — this class is
shared implementation, not a type. A fetcher that has no use for it can satisfy
the Protocol without inheriting.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx

from commonplace._config import DEFAULT_UA
from commonplace._fetch._helpers import (
    Pacer,
    raise_on_session_error,
    raise_unreachable,
    read_chrome_cookies,
    request_with_retry,
)
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._wire import write_archive

ACCEPT_LANGUAGE = "en-GB,en;q=0.9"

#: `socket.create_connection` charges its timeout per resolved address, so
#: connect must stay short where `timeout` can be long. See #18.
CONNECT_TIMEOUT = 5.0


class BaseFetcher:
    """Cookie discovery, browser-shaped HTTP, and archive writing.

    Subclasses declare the provider as class attributes and implement `fetch`.
    Cookies and HTTP transport are injectable — real use passes neither and the
    fetcher discovers cookies from Chrome and uses the real network. Tests
    inject fakes for both."""

    #: Source key: names the archive and `--source`, and pairs it with an Importer.
    source: str
    #: Cookie domain to read from Chrome.
    cookie_domain: str
    #: How the provider is named in messages to the user, and where to log in.
    service_name: str
    login_url: str
    #: The cookie whose presence means the browser is signed in.
    session_cookie: str

    #: Provider headers, sandwiched between User-Agent and Accept-Language by
    #: `_headers`. Ordering matters — see there.
    extra_headers: ClassVar[dict[str, str]] = {}
    timeout: float = 30.0
    follow_redirects: bool = False
    #: Starting gap between requests. Zero costs nothing until the server
    #: objects, at which point [[Pacer]] widens it; only providers known to
    #: challenge bursts need a non-zero value.
    request_interval: float = 0.0

    _client: httpx.Client
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
        self._pacer = Pacer(self.request_interval)

    def _headers(self) -> dict[str, str]:
        """Headers that make a request look like the browser it claims to be.

        Two things matter, both verified against chatgpt.com by changing one
        variable at a time:

        - `Accept-Language` must be present. A Chrome User-Agent without it
          draws a 403: no real browser omits it, so its absence is a bot tell.
        - It must come *last*. Same headers, same values, moved ahead of
          `Accept` and the same request 403s again. Chrome emits it after
          `Accept-Encoding`, and Cloudflare fingerprints the order, not just
          the set.

        Hence the sandwich: `extra_headers` sits between the User-Agent and the
        trailing `Accept-Language`, and subclasses contribute values rather
        than building a header dict of their own. Constructing the client here
        is what makes that unbypassable — the ordering cannot be got wrong by a
        fetcher that never assembles its own headers."""
        return {"User-Agent": self._ua, **self.extra_headers, "Accept-Language": ACCEPT_LANGUAGE}

    def _read_cookies(self) -> dict[str, str]:
        if self._injected_cookies is not None:
            return self._injected_cookies
        return read_chrome_cookies(self.cookie_domain)

    def _report_no_session(self) -> None:
        """Tell the user the browser holds no session cookie for this provider."""
        logger.error(f"No {self.service_name} session cookie found. Log in at {self.login_url} in Chrome first.")

    def _has_session(self, cookies: dict[str, str]) -> bool:
        """Whether `cookies` hold a usable session, having said what's missing if not."""
        if not cookies.get(self.session_cookie):
            self._report_no_session()
            return False
        return True

    def _authorise(self, client: httpx.Client) -> None:
        """Whatever the API needs between opening the client and its first real call; nothing by default."""

    @contextmanager
    def _signed_in(self) -> Iterator[httpx.Client | None]:
        """An authorised client, or None, reported, when the browser holds no session."""
        cookies = self._read_cookies()
        if not self._has_session(cookies):
            yield None
            return
        with self._session(cookies) as client:
            self._authorise(client)
            yield client

    @contextmanager
    def _session(self, cookies: dict[str, str]) -> Iterator[httpx.Client]:
        """Open the client and start a fresh wire log.

        The log resets here rather than in `__init__` so that a fetcher reused
        across runs cannot carry one run's responses into another's archive."""
        self._wire_log = []
        with httpx.Client(
            cookies=cookies,
            headers=self._headers(),
            follow_redirects=self.follow_redirects,
            timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT),
            transport=self._transport,
        ) as client:
            self._client = client
            yield client

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Pace, send, retry transient failures, and turn anything blocking —
        a rejecting response or an unreachable host — into a `FetchBlocked`."""
        self._pacer.wait()
        try:
            r = request_with_retry(self._client, method, url, on_throttled=self._pacer.slow_down, **kwargs)
        except httpx.TransportError as exc:
            raise_unreachable(exc, service_name=self.service_name, login_url=self.login_url)
        raise_on_session_error(r, service_name=self.service_name, login_url=self.login_url)
        return r

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("GET", url, **kwargs)

    def _read_fresh[T](self, fresh: Sequence[T], since: datetime | None, read: Callable[[T], object]) -> None:
        """Say how much is new since the cursor, then `read` each item behind a progress bar."""
        logger.info(f"{len(fresh)} new since {since or 'beginning'}")
        if not fresh:
            return
        for item in track(fresh, f"Fetching {self.source}"):
            read(item)

    def _log(self, **entry: Any) -> None:
        """Record one provider response verbatim. Fetchers interpret nothing;
        see [[commonplace._wire]]."""
        self._wire_log.append(entry)

    def _write_archive(self, destination: Path) -> Path:
        return write_archive(destination / f"{self.source}-wire.jsonl.gz", self.source, self._wire_log)
