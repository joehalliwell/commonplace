"""Fetch conversations directly from claude.ai using the browser session cookie."""

from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx

from commonplace._fetch._base import BaseFetcher
from commonplace._logging import logger


def _provenance(r: httpx.Response) -> dict[str, str]:
    """The `request-id` claude.ai stamps on each response.

    Provider-specific, hence here rather than in [[commonplace._wire]]: it is
    the only identifier tying a capture to Anthropic's own records, and no
    later reader can recover it from the body. Omitted when absent — the
    missing key already says the header wasn't sent."""
    request_id = r.headers.get("request-id")
    return {"request_id": request_id} if request_id else {}


def updated_after(items: list[dict[str, Any]], since: datetime | None) -> list[dict[str, Any]]:
    """The listed items whose `updated_at` is after `since`."""
    return [i for i in items if since is None or datetime.fromisoformat(i["updated_at"]) > since]


class ClaudeSessionFetcher(BaseFetcher):
    """Signs in to claude.ai and calls its organisation API; endpoints are unofficial, so expect drift."""

    cookie_domain = "claude.ai"
    service_name = "Claude"
    login_url = "https://claude.ai"
    session_cookie = "sessionKey"
    extra_headers: ClassVar[dict[str, str]] = {"Accept": "application/json", "Referer": "https://claude.ai/"}

    _org_uuid: str

    def _has_session(self, cookies: dict[str, str]) -> bool:
        """Also records `_org_uuid`: every API path is scoped to the organisation."""
        if not super()._has_session(cookies):
            return False
        org_uuid = cookies.get("lastActiveOrg")
        if not org_uuid:
            logger.error(f"No lastActiveOrg cookie. Visit {self.login_url} in Chrome to set it.")
            return False
        self._org_uuid = org_uuid
        return True

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

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        with self._signed_in() as client:
            if client is None:
                return None
            fresh = self._list_fresh(since)
            self._read_fresh(fresh, since, self._read)

        return self._write_archive(destination) if fresh else None

    def _list_fresh(self, since: datetime | None) -> list[dict[str, Any]]:
        return updated_after(self._api("GET", "chat_conversations", endpoint="conversations").json(), since)

    def _read(self, item: dict[str, Any]) -> None:
        self._api(
            "GET",
            f"chat_conversations/{item['uuid']}",
            endpoint="conversation",
            key={"cid": item["uuid"]},
            params={"tree": "True", "rendering_mode": "raw"},
        )
