"""Fetch conversations directly from chatgpt.com using the browser session cookie."""

from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from commonplace._config import DEFAULT_UA
from commonplace._fetch._helpers import Pacer, raise_on_session_error, read_chrome_cookies, request_with_retry
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._wire import write_archive

SESSION_URL = "https://chatgpt.com/api/auth/session"
LIST_URL = "https://chatgpt.com/backend-api/conversations"
DETAIL_URL = "https://chatgpt.com/backend-api/conversation/{cid}"

# NextAuth splits the session token into `.0`, `.1`, ... once it exceeds ~4KB,
# so the cookie is identified by prefix. httpx sends every chunk and the server
# reassembles them; nothing here needs to join them.
SESSION_COOKIE_PREFIX = "__Secure-next-auth.session-token"

PAGE_SIZE = 100

# Starting gap between requests. Bursting ~3/s over 91 requests drew a
# Cloudflare challenge, so this is deliberately non-zero; it is otherwise a
# guess, and [[Pacer]] widens it if the server ever answers 429. The other two
# providers have not needed pacing.
REQUEST_INTERVAL = 0.25


class ChatGptFetcher:
    """Records one listing page per 100 conversations plus N conversation
    details from chatgpt.com's internal API. Endpoints are unofficial; expect
    drift.

    Unlike the other fetchers, the session cookie is not itself the credential:
    it buys a short-lived bearer token from `/api/auth/session`, which every
    `backend-api` call then carries.

    Cookies and HTTP transport are injectable — real use passes neither and the
    fetcher discovers cookies from Chrome and uses the real network. Tests
    inject fakes for both."""

    source: str = "chatgpt"

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
        self._pacer = Pacer(REQUEST_INTERVAL)

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        cookies = self._injected_cookies if self._injected_cookies is not None else read_chrome_cookies("chatgpt.com")
        if not any(name.startswith(SESSION_COOKIE_PREFIX) for name in cookies):
            logger.error("No ChatGPT session cookie found. Log in at https://chatgpt.com in Chrome first.")
            return None

        self._wire_log = []

        with httpx.Client(
            cookies=cookies,
            headers={
                "User-Agent": self._ua,
                "Accept": "application/json",
                "Referer": "https://chatgpt.com/",
            },
            follow_redirects=True,
            timeout=30.0,
            transport=self._transport,
        ) as self._client:
            self._client.headers["Authorization"] = f"Bearer {self._read_access_token()}"

            fresh = list(self._list_fresh_ids(since))
            logger.info(f"{len(fresh)} conversations new since {since or 'beginning'}")

            if not fresh:
                return None

            for cid in track(fresh, "Fetching conversations"):
                self._fetch_detail(cid)

        return self._write_archive(destination)

    def _read_access_token(self) -> str:
        """Trade the session cookie for the bearer token `backend-api` wants.

        Not recorded to the wire log: it is a credential, and it is not
        conversation material."""
        r = self._get(SESSION_URL)
        token = r.json().get("accessToken")
        if not token:
            raise RuntimeError("No access token in the ChatGPT session response — the auth flow may have changed.")
        return token

    def _list_fresh_ids(self, since: datetime | None):
        """Walk listing pages, yielding ids updated after `since`.

        The listing is ordered by `update_time` descending, so the first stale
        conversation means every later one is stale too and paging can stop.
        Pages are recorded whole either way — the fetcher does not edit what it
        saw, only what it follows up.

        Termination is on a short page, not on the response's `total`. `total`
        is not a count: asking for 3 of 90 conversations reports `total: 4`, so
        it behaves like "items returned, plus one if more exist". Trusting it
        would truncate the walk."""
        offset = 0
        while True:
            items = self._list_page(offset)["items"]
            for item in items:
                # Listing timestamps are ISO strings; detail responses use
                # epoch floats for the same fields.
                if since is not None and datetime.fromisoformat(item["update_time"]) <= since:
                    return
                yield item["id"]
            if len(items) < PAGE_SIZE:
                return
            offset += len(items)

    def _list_page(self, offset: int) -> dict[str, Any]:
        r = self._get(LIST_URL, params={"offset": offset, "limit": PAGE_SIZE, "order": "updated"})
        self._wire_log.append({"endpoint": "conversations", "offset": offset, "response": r.text})
        return r.json()

    def _fetch_detail(self, cid: str) -> None:
        r = self._get(DETAIL_URL.format(cid=cid))
        self._wire_log.append({"endpoint": "conversation", "cid": cid, "response": r.text})

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        self._pacer.wait()
        r = request_with_retry(self._client, "GET", url, on_throttled=self._pacer.slow_down, **kwargs)
        raise_on_session_error(r, service_name="ChatGPT", login_url="https://chatgpt.com")
        return r

    def _write_archive(self, destination: Path) -> Path:
        return write_archive(destination / "chatgpt-wire.jsonl.gz", self.source, self._wire_log)
