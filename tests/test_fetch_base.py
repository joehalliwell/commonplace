"""Tests for the plumbing every fetcher shares.

The per-provider files cover each fetcher's own walk; these cover the
invariants that hold across all of them, so a fourth provider inherits them
rather than rediscovering them.
"""

import httpx
import pytest

from commonplace._fetch._base import BaseFetcher
from commonplace._fetch._chatgpt import ChatGptFetcher
from commonplace._fetch._claude import ClaudeFetcher
from commonplace._fetch._commands import default_fetchers
from commonplace._fetch._gemini import GeminiFetcher
from commonplace._fetch._helpers import FetchBlocked
from commonplace._fetch._types import Fetcher
from commonplace._wire import read_header

FETCHERS = [ChatGptFetcher, ClaudeFetcher, GeminiFetcher]


@pytest.mark.parametrize("fetcher_class", FETCHERS, ids=lambda c: c.source)
def test_accept_language_is_sent_last(fetcher_class):
    """Order is part of the fingerprint, not just the set. The same headers
    with Accept-Language ahead of Accept draw a 403 from the live API, so the
    trailing position is load-bearing — for every provider, since any of them
    may end up behind the same bot check."""
    headers = list(fetcher_class()._headers())

    assert headers[0] == "User-Agent"
    assert headers[-1] == "Accept-Language"


@pytest.mark.parametrize("fetcher_class", FETCHERS, ids=lambda c: c.source)
def test_provider_headers_sit_between_user_agent_and_accept_language(fetcher_class):
    """`extra_headers` is the only variation point, so a provider cannot
    contribute a header that displaces the trailing Accept-Language."""
    headers = fetcher_class()._headers()

    assert set(fetcher_class.extra_headers) <= set(headers)
    assert list(headers)[1:-1] == list(fetcher_class.extra_headers)


@pytest.mark.parametrize("fetcher_class", FETCHERS, ids=lambda c: c.source)
def test_fetchers_satisfy_the_protocol(fetcher_class):
    """The Protocol is the contract; BaseFetcher is only shared implementation."""
    assert isinstance(fetcher_class(), Fetcher)


def test_default_fetchers_cover_every_provider(test_repo):
    assert {f.source for f in default_fetchers(test_repo.config)} == {c.source for c in FETCHERS}


class _StubFetcher(BaseFetcher):
    """Minimal concrete fetcher for exercising the base class directly."""

    source = "stub"
    cookie_domain = "example.com"
    service_name = "Stub"
    login_url = "https://example.com"


def _stub(handler) -> _StubFetcher:
    return _StubFetcher(cookies={"session": "x"}, transport=httpx.MockTransport(handler))


def test_archive_is_named_for_the_source(tmp_path):
    fetcher = _stub(lambda r: httpx.Response(200, text="{}"))
    with fetcher._session({"session": "x"}):
        fetcher._log(endpoint="thing", response="{}")
    archive = fetcher._write_archive(tmp_path)

    assert archive.name == "stub-wire.jsonl.gz"
    assert read_header(archive)[0] == "stub"


def test_a_second_run_does_not_inherit_the_first_runs_wire_log(tmp_path):
    """The log resets per session, so a reused fetcher cannot write one run's
    responses into another run's archive."""
    fetcher = _stub(lambda r: httpx.Response(200, text="{}"))

    with fetcher._session({"session": "x"}):
        fetcher._log(endpoint="first", response="{}")
    with fetcher._session({"session": "x"}):
        fetcher._log(endpoint="second", response="{}")

    assert [e["endpoint"] for e in fetcher._wire_log] == ["second"]


def test_blocked_requests_name_the_service_and_login_url(tmp_path):
    """Every fetcher gets remediation text built from its own class attributes."""
    fetcher = _stub(lambda r: httpx.Response(403, text="{}"))

    with fetcher._session({"session": "x"}), pytest.raises(FetchBlocked) as excinfo:
        fetcher._get("https://example.com/api")

    assert "Stub" in str(excinfo.value)
    assert "https://example.com" in str(excinfo.value)


def test_a_429_widens_pacing_for_every_fetcher(no_retry_sleep):
    """Claude and Gemini start at a zero interval — free until the server
    objects — but must still react when it does."""
    calls = {"n": 0}

    def throttle_once(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429 if calls["n"] == 1 else 200, text="{}")

    fetcher = _stub(throttle_once)
    assert fetcher._pacer.interval == 0.0

    with fetcher._session({"session": "x"}):
        fetcher._get("https://example.com/api")

    assert fetcher._pacer.interval > 0.0
