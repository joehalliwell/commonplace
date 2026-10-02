"""Fetch conversations directly from claude.ai using the browser session cookie."""

from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx

from commonplace._fetch._base import BaseFetcher
from commonplace._logging import logger
from commonplace._progress import track


def _provenance(r: httpx.Response) -> dict[str, str]:
    """The `request-id` claude.ai stamps on each response.

    Provider-specific, hence here rather than in [[commonplace._wire]]: it is
    the only identifier tying a capture to Anthropic's own records, and no
    later reader can recover it from the body. Omitted when absent — the
    missing key already says the header wasn't sent."""
    request_id = r.headers.get("request-id")
    return {"request_id": request_id} if request_id else {}


class ClaudeSessionFetcher(BaseFetcher):
    """The walk every claude.ai fetcher makes: one listing, then a read per item newer than the cursor.

    Subclasses name the endpoints by implementing `_list` and `_read`. Endpoints
    are unofficial; expect drift."""

    cookie_domain = "claude.ai"
    service_name = "Claude"
    login_url = "https://claude.ai"
    extra_headers: ClassVar[dict[str, str]] = {"Accept": "application/json", "Referer": "https://claude.ai/"}

    #: Whether a listing with nothing new is still worth an archive.
    archive_when_unchanged: bool = False

    _org_uuid: str

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        cookies = self._authenticate()
        if cookies is None:
            return None

        with self._session(cookies):
            items = self._list()
            fresh = [i for i in items if since is None or datetime.fromisoformat(i["updated_at"]) > since]
            logger.info(f"{len(fresh)}/{len(items)} new since {since or 'beginning'}")

            if not fresh and not self.archive_when_unchanged:
                return None

            for item in track(fresh, f"Fetching {self.source}"):
                self._read(item)

        return self._write_archive(destination)

    def _list(self) -> list[dict[str, Any]]:
        """Record the listing and return its items, each carrying `updated_at`."""
        raise NotImplementedError

    def _read(self, item: dict[str, Any]) -> None:
        """Record the full response for one listed item."""
        raise NotImplementedError

    def _authenticate(self) -> dict[str, str] | None:
        """The session's cookies, with `_org_uuid` set — or `None`, having said why, if there is no usable session."""
        cookies = self._read_cookies()
        org_uuid = cookies.get("lastActiveOrg")
        if not cookies.get("sessionKey"):
            logger.error("No Claude session cookie found. Log in at https://claude.ai in Chrome first.")
            return None
        if not org_uuid:
            logger.error("No lastActiveOrg cookie. Visit https://claude.ai in Chrome to set it.")
            return None
        self._org_uuid = org_uuid
        return cookies

    def _api(
        self, method: str, path: str, *, endpoint: str, key: dict[str, str] | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Call the organisation's API and log the response verbatim under `endpoint` and `key`."""
        r = self._request(method, f"https://claude.ai/api/organizations/{self._org_uuid}/{path}", **kwargs)
        self._log(endpoint=endpoint, **(key or {}), **_provenance(r), response=r.text)
        return r


class ClaudeFetcher(ClaudeSessionFetcher):
    """Records one list call plus N conversation details."""

    source = "claude"

    def _list(self) -> list[dict[str, Any]]:
        return self._api("GET", "chat_conversations", endpoint="conversations").json()

    def _read(self, item: dict[str, Any]) -> None:
        self._api(
            "GET",
            f"chat_conversations/{item['uuid']}",
            endpoint="conversation",
            key={"cid": item["uuid"]},
            params={"tree": "True", "rendering_mode": "raw"},
        )
