"""Fetch conversations directly from chatgpt.com using the browser session cookie."""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx

from commonplace._fetch._base import BaseFetcher

SESSION_URL = "https://chatgpt.com/api/auth/session"
LIST_URL = "https://chatgpt.com/backend-api/conversations"
DETAIL_URL = "https://chatgpt.com/backend-api/conversation/{cid}"

PAGE_SIZE = 100


class ChatGptSessionFetcher(BaseFetcher):
    """Signs in to chatgpt.com's internal `backend-api`; endpoints are unofficial, so expect drift.

    The session cookie is not itself the credential: it buys a short-lived
    bearer token from `/api/auth/session`, which every `backend-api` call then
    carries."""

    cookie_domain = "chatgpt.com"
    service_name = "ChatGPT"
    login_url = "https://chatgpt.com"
    # NextAuth splits the session token into `.0`, `.1`, ... once it exceeds
    # ~4KB, so this is a prefix. httpx sends every chunk and the server
    # reassembles them; nothing here needs to join them.
    session_cookie = "__Secure-next-auth.session-token"
    extra_headers: ClassVar[dict[str, str]] = {"Accept": "application/json", "Referer": "https://chatgpt.com/"}
    follow_redirects = True

    # Bursting ~3/s over 91 requests drew a Cloudflare challenge, so this is
    # deliberately non-zero; it is otherwise a guess. The other two providers
    # have not needed pacing.
    request_interval = 0.25

    def _has_session(self, cookies: dict[str, str]) -> bool:
        """Matched by prefix, since NextAuth may have chunked the cookie."""
        if not any(name.startswith(self.session_cookie) for name in cookies):
            self._report_no_session()
            return False
        return True

    def _authorise(self, client: httpx.Client) -> None:
        """Trade the session cookie for the bearer token `backend-api` wants.

        Not recorded to the wire log: it is a credential, and it is not
        conversation material."""
        token = self._get(SESSION_URL).json().get("accessToken")
        if not token:
            raise RuntimeError("No access token in the ChatGPT session response — the auth flow may have changed.")
        client.headers["Authorization"] = f"Bearer {token}"


class ChatGptFetcher(ChatGptSessionFetcher):
    """Records one listing page per 100 conversations plus N conversation details."""

    source = "chatgpt"

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        with self._signed_in() as client:
            if client is None:
                return None
            fresh = list(self._list_fresh(since))
            self._read_fresh(fresh, since, self._read)

        return self._write_archive(destination) if fresh else None

    def _list_fresh(self, since: datetime | None) -> Iterator[str]:
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
        self._log(endpoint="conversations", offset=offset, response=r.text)
        return r.json()

    def _read(self, cid: str) -> None:
        r = self._get(DETAIL_URL.format(cid=cid))
        self._log(endpoint="conversation", cid=cid, response=r.text)
