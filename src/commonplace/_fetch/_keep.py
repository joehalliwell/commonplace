"""Fetch Google Keep notes from the endpoint keep.google.com's own web app syncs with.

Keep has no API for personal accounts, so this does what the web app does: POST to `notes/v1/changes` on
`notes-pa.clients6.google.com`, signed with the Google session cookies and a `SAPISIDHASH` derived from
them, with a real `Origin` of keep.google.com. An `X-Origin` header instead draws "Origin doesn't match
Host for XD3": that's the cross-domain proxy's header, not a direct call's. A sync arrives in pages; each
names the version to ask from next, until one is no longer `truncated`.

Given a version, Keep sends only what changed since, verbatim, trashed and deleted notes included. So a
fetch asks from the version its last capture reached, and stores a change set of a few KB rather than the
whole of Keep; the importer replays the chain on the last full sync. A full sync starts the chain again
when there's none, when it has grown long enough that replaying it costs more than a checkpoint, or when
Keep asks for one.
"""

import hashlib
import random
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import httpx

from commonplace._fetch._base import BaseFetcher
from commonplace._fetch._helpers import upstream_changed
from commonplace._import._keep import last_version, since_last_full

ORIGIN = "https://keep.google.com"
CHANGES_URL = "https://notes-pa.clients6.google.com/notes/v1/changes"
#: The web app's own browser key, served in its JavaScript to every visitor: an identifier, not a secret.
WEB_KEY = "AIzaSyDE7NHMUZfMoJVu-YNkK-7AXFSuL1Q9gKE"
#: What the web app says it can render; Keep tailors what it sends to these.
CAPABILITIES = ("NC", "PI", "LB", "AN", "SH", "DR", "TR", "IN", "SNB", "MI", "CO")
#: Change sets after which the next fetch is a full sync again, so a replay stays short.
CHECKPOINT_EVERY = 30


class KeepFetcher(BaseFetcher):
    """Records every page of one sync of Keep: all of it, or what changed since the last capture."""

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

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        # `since` goes unused: Keep's own version, from the last capture, says what's new far more exactly.
        chain = since_last_full(previous)
        checkpoint = not chain or len(chain) > CHECKPOINT_EVERY
        resume = None if checkpoint else last_version(chain[-1])
        with self._signed_in():
            if not self._sync(resume):
                self._wire_log.clear()  # Keep asked to start over: only the full sync it gets is the capture
                self._sync(None)
        return [self._write_archive(destination)]

    def _sync(self, target: str | None) -> bool:
        """Page through the sync from `target` (None: everything); False if Keep asks for a full sync instead."""
        while True:
            page = self._changes(target)
            if target is not None and page.get("forceFullResync"):
                return False
            if not page.get("truncated"):
                return True
            if page["toVersion"] == target:
                raise upstream_changed(self.service_name, self.login_url, "a sync page that didn't advance")
            target = page["toVersion"]

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
