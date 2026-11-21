"""Fetch conversations directly from claude.ai using the browser session cookie."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx

from commonplace._fetch._base import BaseFetcher
from commonplace._fetch._helpers import session_rejected

#: Each kind of chat to list: a scheduled task's run is one, but only listed when asked for.
PLATFORMS = [("platforms", "CLAUDE_AI"), ("platforms", "ROUTINE_RUN")]


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

    def _check_session(self, cookies: httpx.Cookies) -> None:
        """Also roots `_api` at the organisation, which scopes every API path."""
        super()._check_session(cookies)
        org_uuid = cookies.get("lastActiveOrg")
        if not org_uuid:
            raise session_rejected(self.service_name, self.login_url, ": Chrome holds no lastActiveOrg cookie")
        self.api_root = f"https://claude.ai/api/organizations/{org_uuid}"

    def _provenance(self, r: httpx.Response) -> dict[str, str]:
        """The `request-id` claude.ai stamps on each response.

        The only identifier tying a capture to Anthropic's own records, and no
        later reader can recover it from the body. Omitted when absent — the
        missing key already says the header wasn't sent."""
        request_id = r.headers.get("request-id")
        return {"request_id": request_id} if request_id else {}


class ClaudeFetcher(ClaudeSessionFetcher):
    """Records one list call plus N conversation details."""

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        with self._signed_in():
            fresh = self._list_fresh(since)
            self._read_fresh(fresh, since, self._read)

        return [self._write_archive(destination)] if fresh else []

    def _list_fresh(self, since: datetime | None) -> list[dict[str, Any]]:
        listing = self._api("GET", "chat_conversations", endpoint="conversations", params=PLATFORMS)
        return updated_after(listing.json(), since)

    def _read(self, item: dict[str, Any]) -> None:
        self._api(
            "GET",
            f"chat_conversations/{item['uuid']}",
            endpoint="conversation",
            key={"cid": item["uuid"]},
            # `raw` rendering replaces each tool call with a placeholder.
            params={"tree": "True", "rendering_mode": "messages", "render_all_tools": "true"},
        )
