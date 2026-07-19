"""Tests for the Claude fetcher (and its paired importer)."""

from pathlib import Path

import httpx
import pytest

from commonplace._fetch._claude import ClaudeFetcher
from commonplace._import._claude import ClaudeImporter

ORG = "org-uuid-1"

SUMMARIES = [
    {"uuid": "c-old", "name": "Old", "updated_at": "2026-06-01T00:00:00Z"},
    {"uuid": "c-new", "name": "New", "updated_at": "2026-07-15T00:00:00Z"},
]

TEST_COOKIES = {"sessionKey": "sk-test", "lastActiveOrg": ORG}


def _detail(uuid: str) -> dict:
    return {
        "uuid": uuid,
        "name": f"Chat {uuid}",
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
        "chat_messages": [
            {
                "uuid": "m1",
                "sender": "human",
                "text": f"Hello from {uuid}",
                "created_at": "2026-07-15T00:00:00Z",
            },
            {
                "uuid": "m2",
                "sender": "assistant",
                "text": f"Hi from {uuid}",
                "created_at": "2026-07-15T00:00:01Z",
            },
        ],
    }


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == f"/api/organizations/{ORG}/chat_conversations":
        return httpx.Response(200, json=SUMMARIES)
    prefix = f"/api/organizations/{ORG}/chat_conversations/"
    if path.startswith(prefix):
        uuid = path[len(prefix) :]
        return httpx.Response(200, json=_detail(uuid))
    return httpx.Response(404)


def _make_fetcher(handler=_handler, cookies=TEST_COOKIES) -> ClaudeFetcher:
    return ClaudeFetcher(cookies=cookies, transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Unit tests on the shape-normalisation helper.
# ---------------------------------------------------------------------------


def test_to_export_shape_wraps_flat_text():
    """API messages carry a flat text field; the importer expects blocks."""
    convo = {"chat_messages": [{"sender": "human", "text": "hi"}]}
    result = ClaudeFetcher._to_export_shape(convo)
    assert result["chat_messages"][0]["content"] == [{"type": "text", "text": "hi"}]


def test_to_export_shape_preserves_existing_content():
    """Don't clobber messages that already have content blocks."""
    blocks = [{"type": "text", "text": "hi", "citations": []}]
    convo = {"chat_messages": [{"sender": "human", "text": "hi", "content": blocks}]}
    result = ClaudeFetcher._to_export_shape(convo)
    assert result["chat_messages"][0]["content"] is blocks


def test_archive_is_valid_claude_export(tmp_path):
    """Synthesized ZIP must be recognized by the existing importer."""
    archive = ClaudeFetcher._write_archive([ClaudeFetcher._to_export_shape(_detail("c-1"))], tmp_path)
    importer = ClaudeImporter()
    assert importer.can_import(archive)
    assert len(importer.import_(archive)) == 1


# ---------------------------------------------------------------------------
# Fetcher tests — cookies + transport injected via the constructor.
# ---------------------------------------------------------------------------


def test_fetch_returns_none_without_session(tmp_path):
    fetcher = ClaudeFetcher(cookies={})
    assert fetcher.fetch(tmp_path, since=None) is None


def test_fetch_returns_none_without_org(tmp_path):
    fetcher = ClaudeFetcher(cookies={"sessionKey": "sk"})
    assert fetcher.fetch(tmp_path, since=None) is None


def test_fetch_end_to_end(tmp_path):
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None
    assert ClaudeImporter().can_import(archive)
    assert len(ClaudeImporter().import_(archive)) == 2


def test_fetch_incremental_skips_seen(tmp_path):
    """Cursor at or after latest summary → nothing to fetch."""
    assert _make_fetcher().fetch(tmp_path, since="2026-07-15T00:00:00Z") is None


def test_fetch_incremental_picks_up_newer(tmp_path):
    """Cursor between the two summaries → only the newer one."""
    archive = _make_fetcher().fetch(tmp_path, since="2026-06-15T00:00:00Z")
    assert archive is not None
    logs = ClaudeImporter().import_(archive)
    assert len(logs) == 1
    assert logs[0].metadata["uuid"] == "c-new"


def test_fetch_command_dispatches(test_repo):
    """`commonplace fetch` runs configured fetchers and imports the result."""
    from commonplace._fetch._commands import fetch

    fetch(test_repo, fetchers=[_make_fetcher()], auto_index=False)

    chats = list((Path(test_repo.root) / "chats" / "claude").rglob("*.md"))
    assert len(chats) == 2


def test_fetch_command_filters_by_source(test_repo):
    from commonplace._fetch._commands import fetch

    called: list[str] = []

    class Stub:
        source = "stub"

        def fetch(self, destination, since):
            called.append("stub")
            return None

    fetch(test_repo, sources=["nonexistent"], fetchers=[Stub()], auto_index=False)
    assert called == []

    fetch(test_repo, sources=["stub"], fetchers=[Stub()], auto_index=False)
    assert called == ["stub"]


def test_fetch_retries_transient_5xx(monkeypatch, tmp_path):
    """A 503 followed by success should resolve without raising."""
    monkeypatch.setattr("commonplace._fetch._helpers.time.sleep", lambda _: None)

    calls: dict[str, int] = {}

    def flaky(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls[path] = calls.get(path, 0) + 1
        if path == f"/api/organizations/{ORG}/chat_conversations":
            return httpx.Response(200, json=SUMMARIES)
        if calls[path] == 1:
            return httpx.Response(503)
        prefix = f"/api/organizations/{ORG}/chat_conversations/"
        uuid = path[len(prefix) :]
        return httpx.Response(200, json=_detail(uuid))

    archive = _make_fetcher(handler=flaky).fetch(tmp_path, since=None)
    assert archive is not None
    assert len(ClaudeImporter().import_(archive)) == 2


def test_fetch_raises_on_401(tmp_path):
    with pytest.raises(RuntimeError, match="session expired"):
        _make_fetcher(handler=lambda r: httpx.Response(401)).fetch(tmp_path, since=None)
