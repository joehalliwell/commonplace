"""Tests for the fetch pipeline (Claude fetcher + commands)."""

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


@pytest.fixture
def mock_http(monkeypatch):
    """Patch httpx.Client inside _claude to route through MockTransport."""
    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("commonplace._fetch._claude.httpx.Client", factory)


@pytest.fixture
def stub_cookies(monkeypatch):
    """Bypass real browser cookie extraction."""
    monkeypatch.setattr(
        "commonplace._fetch._claude.read_chrome_cookies",
        lambda domain: {"sessionKey": "sk-test", "lastActiveOrg": ORG},
    )


@pytest.fixture
def stub_cursor(monkeypatch):
    """Return a settable cursor so tests can simulate prior imports."""
    state = {"value": None}

    def setter(ts):
        state["value"] = ts

    monkeypatch.setattr("commonplace._fetch._claude.last_import_time", lambda repo, source: state["value"])
    return setter


def test_to_export_shape_wraps_flat_text():
    """API messages carry a flat text field; the importer expects blocks."""
    convo = {"chat_messages": [{"sender": "human", "text": "hi"}]}
    result = ClaudeFetcher()._to_export_shape(convo)
    assert result["chat_messages"][0]["content"] == [{"type": "text", "text": "hi"}]


def test_to_export_shape_preserves_existing_content():
    """Don't clobber messages that already have content blocks."""
    blocks = [{"type": "text", "text": "hi", "citations": []}]
    convo = {"chat_messages": [{"sender": "human", "text": "hi", "content": blocks}]}
    result = ClaudeFetcher()._to_export_shape(convo)
    assert result["chat_messages"][0]["content"] is blocks


def test_archive_is_valid_claude_export(tmp_path):
    """Synthesized ZIP must be recognized by the existing importer."""
    fetcher = ClaudeFetcher()
    archive = fetcher._write_archive([fetcher._to_export_shape(_detail("c-1"))], tmp_path)
    importer = ClaudeImporter()
    assert importer.can_import(archive)
    logs = importer.import_(archive)
    assert len(logs) == 1


def test_fetch_returns_none_without_session(monkeypatch, test_repo, tmp_path):
    monkeypatch.setattr("commonplace._fetch._claude.read_chrome_cookies", lambda domain: {})
    assert ClaudeFetcher().fetch(tmp_path, test_repo) is None


def test_fetch_returns_none_without_org(monkeypatch, test_repo, tmp_path):
    monkeypatch.setattr("commonplace._fetch._claude.read_chrome_cookies", lambda domain: {"sessionKey": "sk"})
    assert ClaudeFetcher().fetch(tmp_path, test_repo) is None


def test_fetch_end_to_end(mock_http, stub_cookies, stub_cursor, test_repo, tmp_path):
    """With no prior import, fetch pulls everything."""
    archive = ClaudeFetcher().fetch(tmp_path, test_repo)
    assert archive is not None
    assert ClaudeImporter().can_import(archive)
    assert len(ClaudeImporter().import_(archive)) == 2


def test_fetch_incremental_skips_seen(mock_http, stub_cookies, stub_cursor, test_repo, tmp_path):
    """Cursor at or after latest summary → nothing to fetch."""
    stub_cursor("2026-07-15T00:00:00Z")
    assert ClaudeFetcher().fetch(tmp_path, test_repo) is None


def test_fetch_incremental_picks_up_newer(mock_http, stub_cookies, stub_cursor, test_repo, tmp_path):
    """Cursor between the two summaries → only the newer one."""
    stub_cursor("2026-06-15T00:00:00Z")
    archive = ClaudeFetcher().fetch(tmp_path, test_repo)
    assert archive is not None
    logs = ClaudeImporter().import_(archive)
    assert len(logs) == 1
    assert logs[0].metadata["uuid"] == "c-new"


def test_last_import_time_returns_none_on_fresh_repo(test_repo):
    """Fresh repo with no chats/claude/ commits → None cursor."""
    from commonplace._fetch._helpers import last_import_time

    assert last_import_time(test_repo, "claude") is None


def test_last_import_time_returns_iso_after_commit(test_repo):
    """After importing chats, the cursor is an ISO timestamp."""
    from commonplace._fetch._helpers import last_import_time

    (test_repo.root / "chats" / "claude" / "2026" / "07").mkdir(parents=True)
    note = test_repo.root / "chats" / "claude" / "2026" / "07" / "test.md"
    note.write_text("# test\n")
    test_repo.git.index.add(note.relative_to(test_repo.root).as_posix())
    test_repo.commit("Import test", auto_index=False)

    ts = last_import_time(test_repo, "claude")
    assert ts is not None
    assert "T" in ts  # rough ISO shape check


def test_fetch_command_dispatches(test_repo, mock_http, stub_cookies, stub_cursor):
    """`commonplace fetch` runs configured fetchers and imports the result."""
    from commonplace._fetch._commands import fetch

    # Restrict to claude so Gemini's fetcher (which would try real network) is skipped.
    fetch(test_repo, sources=["claude"], auto_index=False)

    chats = list((Path(test_repo.root) / "chats" / "claude").rglob("*.md"))
    assert len(chats) == 2


def test_fetch_command_filters_by_source(test_repo, monkeypatch):
    from commonplace._fetch import _commands

    called: list[str] = []

    class Stub:
        source = "stub"

        def fetch(self, destination, repo):
            called.append("stub")
            return None

    monkeypatch.setattr(_commands, "FETCHERS", [Stub()])
    _commands.fetch(test_repo, sources=["nonexistent"], auto_index=False)
    assert called == []

    _commands.fetch(test_repo, sources=["stub"], auto_index=False)
    assert called == ["stub"]


def test_fetch_retries_transient_5xx(monkeypatch, stub_cookies, stub_cursor, test_repo, tmp_path):
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

    transport = httpx.MockTransport(flaky)
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("commonplace._fetch._claude.httpx.Client", factory)

    archive = ClaudeFetcher().fetch(tmp_path, test_repo)
    assert archive is not None
    assert len(ClaudeImporter().import_(archive)) == 2


def test_fetch_raises_on_401(monkeypatch, stub_cookies, stub_cursor, test_repo, tmp_path):
    def handler(request):
        return httpx.Response(401)

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("commonplace._fetch._claude.httpx.Client", factory)

    with pytest.raises(RuntimeError, match="session expired"):
        ClaudeFetcher().fetch(tmp_path, test_repo)
