"""Tests for the Claude fetcher (and its paired importer)."""

import gzip
import json
from pathlib import Path

import httpx
import pytest

from commonplace._fetch._claude import ClaudeFetcher
from commonplace._import._claude import ClaudeImporter
from commonplace._import._claude_export import ClaudeExportImporter

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


def _read_wire(archive: Path) -> list[dict]:
    with gzip.open(archive, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Fetcher tests — cookies + transport injected via the constructor.
# ---------------------------------------------------------------------------


def test_fetch_returns_none_without_session(tmp_path):
    fetcher = ClaudeFetcher(cookies={})
    assert fetcher.fetch(tmp_path, since=None) is None


def test_fetch_returns_none_without_org(tmp_path):
    fetcher = ClaudeFetcher(cookies={"sessionKey": "sk"})
    assert fetcher.fetch(tmp_path, since=None) is None


def test_fetch_writes_raw_wire_only(tmp_path):
    """Archive is a JSONL of raw API responses — no invented intermediate."""
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None
    assert archive.name == "claude-wire.jsonl.gz"

    wire = _read_wire(archive)
    # 1 list call + 2 details for the two summaries.
    assert [e["endpoint"] for e in wire] == ["conversations", "conversation", "conversation"]
    assert wire[0]["response"] == SUMMARIES
    assert wire[1]["cid"] == "c-old"
    assert wire[2]["cid"] == "c-new"


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

    fetch(test_repo, sources=["nonexistent"], fetchers=[Stub()], auto_index=False)
    assert called == []

    fetch(test_repo, sources=["stub"], fetchers=[Stub()], auto_index=False)
    assert called == ["stub"]


def test_fetch_command_all_flag_bypasses_cursor(test_repo):
    """With all_=True, the fetcher is called with since=None regardless of
    what the repo's git history would otherwise say."""
    from commonplace._fetch._commands import fetch

    calls: list[str | None] = []

    class RecordingStub:
        source = "recording"

        def fetch(self, destination, since):
            calls.append(since)

    # Seed the repo with a chats/recording/ commit so last_commit_time would
    # return a non-None cursor without --all.
    (test_repo.root / "chats" / "recording").mkdir(parents=True)
    note = test_repo.root / "chats" / "recording" / "seed.md"
    note.write_text("# seed\n")
    test_repo.git.index.add(note.relative_to(test_repo.root).as_posix())
    test_repo.commit("Seed recording", auto_index=False)

    fetch(test_repo, fetchers=[RecordingStub()], auto_index=False)
    assert calls[-1] is not None, "without --all, cursor should reflect the seed commit"

    fetch(test_repo, fetchers=[RecordingStub()], auto_index=False, all_=True)
    assert calls[-1] is None, "with --all, cursor is bypassed"


def test_fetch_retries_transient_5xx(no_retry_sleep, tmp_path):
    """A 503 followed by success should resolve without raising."""
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
    with pytest.raises(RuntimeError, match="session rejected"):
        _make_fetcher(handler=lambda r: httpx.Response(401)).fetch(tmp_path, since=None)


# ---------------------------------------------------------------------------
# Importer tests — ClaudeImporter (fetcher wire) and ClaudeExportImporter (ZIP).
# ---------------------------------------------------------------------------


def test_wire_importer_accepts_fetcher_output(tmp_path):
    path = tmp_path / "claude-wire.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"endpoint": "conversations", "response": []}) + "\n")
    assert ClaudeImporter().can_import(path)


def test_wire_importer_rejects_arbitrary_jsonl_gz(tmp_path):
    path = tmp_path / "other.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"not": "ours"}) + "\n")
    assert not ClaudeImporter().can_import(path)


def test_wire_importer_wraps_flat_text(tmp_path):
    """Fetcher-wire messages have only `text`; the importer wraps into blocks."""
    thread = {
        "uuid": "abc",
        "name": "Hi",
        "created_at": "2026-07-15T00:00:00Z",
        "chat_messages": [
            {"sender": "human", "text": "hello", "created_at": "2026-07-15T00:00:00Z"},
            {"sender": "assistant", "text": "hi back", "created_at": "2026-07-15T00:00:01Z"},
        ],
    }
    path = tmp_path / "claude-wire.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"endpoint": "conversations", "response": []}) + "\n")
        f.write(json.dumps({"endpoint": "conversation", "cid": "abc", "response": thread}) + "\n")

    logs = ClaudeImporter().import_(path)
    assert len(logs) == 1
    assert [e.content for e in logs[0].events] == ["hello", "hi back"]


def test_export_importer_requires_users_json(tmp_path):
    """A ZIP with only conversations.json (like ChatGPT's export) is rejected."""
    from zipfile import ZipFile

    path = tmp_path / "not-claude.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", "[]")
    assert not ClaudeExportImporter().can_import(path)


def test_export_importer_accepts_full_pair(tmp_path):
    from zipfile import ZipFile

    path = tmp_path / "claude-export.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", "[]")
        zf.writestr("users.json", "[]")
    assert ClaudeExportImporter().can_import(path)


def test_export_importer_preserves_content_blocks(tmp_path):
    """Export-ZIP messages carry populated content blocks — importer uses
    them directly rather than falling back to flat `text`."""
    from zipfile import ZipFile

    thread = {
        "uuid": "abc",
        "name": "Hi",
        "created_at": "2026-07-15T00:00:00Z",
        "chat_messages": [
            {
                "sender": "human",
                "text": "ignored",  # export has both; importer prefers content
                "created_at": "2026-07-15T00:00:00Z",
                "content": [{"type": "text", "text": "real user text"}],
            },
        ],
    }
    path = tmp_path / "claude-export.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", json.dumps([thread]))
        zf.writestr("users.json", "[]")

    logs = ClaudeExportImporter().import_(path)
    assert logs[0].events[0].content == "real user text"
