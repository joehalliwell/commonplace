"""Fetch Google Keep notes from the endpoint keep.google.com's own web app syncs with.

Keep has no API for personal accounts, so this does what the web app does: POST to `notes/v1/changes` on
`notes-pa.clients6.google.com`, signed with the Google session cookies and a `SAPISIDHASH` derived from
them, with a real `Origin` of keep.google.com. An `X-Origin` header instead draws "Origin doesn't match
Host for XD3": that's the cross-domain proxy's header, not a direct call's. A full sync arrives in pages;
each names the version to ask from next, until one is no longer `truncated`.
"""

import hashlib
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import httpx

from commonplace._fetch._base import BaseFetcher
from commonplace._fetch._helpers import upstream_changed

ORIGIN = "https://keep.google.com"
CHANGES_URL = "https://notes-pa.clients6.google.com/notes/v1/changes"
#: The web app's own browser key, served in its JavaScript to every visitor: an identifier, not a secret.
WEB_KEY = "AIzaSyDE7NHMUZfMoJVu-YNkK-7AXFSuL1Q9gKE"
#: What the web app says it can render; Keep tailors what it sends to these.
CAPABILITIES = ("NC", "PI", "LB", "AN", "SH", "DR", "TR", "IN", "SNB", "MI", "CO")


class KeepFetcher(BaseFetcher):
    """Records every page of one full sync of Keep, so the mirror sees every note and can prune the rest."""

    source = "keep"
    cookie_domain = ".google.com"
    service_name = "Google Keep"
    login_url = ORIGIN
    #: SAPISID signs the request; without it there's nothing to sign with.
    session_cookie = "SAPISID"
    extra_headers: ClassVar[dict[str, str]] = {"Origin": ORIGIN, "Referer": f"{ORIGIN}/"}

    def _authorise(self, client: httpx.Client) -> None:
        """Sign the session as the web app does: SHA-1 of the time, the SAPISID cookie and the origin."""
        sapisid = next(cookie.value for cookie in client.cookies.jar if cookie.name == self.session_cookie)
        stamp = int(time.time())
        digest = hashlib.sha1(f"{stamp} {sapisid} {ORIGIN}".encode()).hexdigest()
        client.headers["Authorization"] = f"SAPISIDHASH {stamp}_{digest}"

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        # `since` goes unused: the mirror needs the whole listing to see a deletion.
        with self._signed_in():
            target: str | None = None
            while True:
                page = self._changes(target)
                if not page.get("truncated"):
                    break
                if page["toVersion"] == target:
                    raise upstream_changed(self.service_name, self.login_url, "a sync page that didn't advance")
                target = page["toVersion"]
        return self._write_archive(destination)

    def _changes(self, target: str | None) -> dict:
        """One page of the sync from `target` (None: from the start), recorded verbatim."""
        body: dict = {
            "nodes": [],  # Nothing sent: Keep only reports what it has
            "clientTimestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "requestHeader": {
                "clientSessionId": f"s--{int(time.time() * 1000)}--{random.randint(10**9, 10**10 - 1)}",
                "clientPlatform": "WEB",
                "clientVersion": {"major": "9", "minor": "9", "build": "9", "revision": "9"},
                "capabilities": [{"type": capability} for capability in CAPABILITIES],
            },
        }
        if target is not None:
            body["targetVersion"] = target
        r = self._request("POST", CHANGES_URL, params={"alt": "json", "key": WEB_KEY}, json=body)
        self._log(endpoint="changes", targetVersion=target, response=r.text)
        return r.json()
