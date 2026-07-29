"""Tests for the wire archive format shared by all fetchers."""

import gzip
import json
from pathlib import Path

from commonplace._import._claude import ClaudeImporter
from commonplace._import._gemini import GeminiImporter
from commonplace._wire import LEGACY_VERSION, WIRE_VERSION, read_entries, read_header, write_archive

ENTRIES = [
    {"endpoint": "conversations", "response": "[]"},
    {"endpoint": "conversation", "cid": "abc", "response": "{}"},
]


def _write_legacy(path: Path, entries: list[dict]) -> Path:
    """A pre-versioning archive: no header line."""
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


def test_write_archive_leads_with_a_header(tmp_path):
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    with gzip.open(archive, "rt", encoding="utf-8") as f:
        first = json.loads(f.readline())
    assert first == {"wire": "claude", "version": WIRE_VERSION}


def test_read_header_returns_source_and_version(tmp_path):
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    assert read_header(archive) == ("claude", WIRE_VERSION)


def test_read_header_treats_missing_header_as_legacy(tmp_path):
    archive = _write_legacy(tmp_path / "claude-wire.jsonl.gz", ENTRIES)
    assert read_header(archive) == (None, LEGACY_VERSION)


def test_read_header_on_unrelated_file(tmp_path):
    path = tmp_path / "other.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"not": "ours"}) + "\n")
    assert read_header(path) == (None, LEGACY_VERSION)


def test_read_entries_skips_the_header(tmp_path):
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    assert list(read_entries(archive)) == ENTRIES


def test_read_entries_yields_every_line_of_a_legacy_archive(tmp_path):
    archive = _write_legacy(tmp_path / "claude-wire.jsonl.gz", ENTRIES)
    assert list(read_entries(archive)) == ENTRIES


def test_write_archive_preserves_non_ascii(tmp_path):
    entries = [{"endpoint": "conversation", "response": '{"name": "Café"}'}]
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", entries)
    assert list(read_entries(archive)) == entries


def test_importers_do_not_claim_each_others_archives(tmp_path):
    """The header makes provider identity declared rather than inferred from
    entry keys, which several providers would otherwise share."""
    claude = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    gemini = write_archive(tmp_path / "gemini-wire.jsonl.gz", "gemini", [{"rpc": "MaZiqc", "response": ""}])

    assert ClaudeImporter().can_import(claude)
    assert not ClaudeImporter().can_import(gemini)
    assert GeminiImporter().can_import(gemini)
    assert not GeminiImporter().can_import(claude)


def test_importers_still_claim_legacy_archives(tmp_path):
    """Archives fetched before versioning are committed in users' repos."""
    claude = _write_legacy(tmp_path / "claude-wire.jsonl.gz", ENTRIES)
    gemini = _write_legacy(tmp_path / "gemini-wire.jsonl.gz", [{"rpc": "MaZiqc", "response": ""}])

    assert ClaudeImporter().can_import(claude)
    assert GeminiImporter().can_import(gemini)
    assert not ClaudeImporter().can_import(gemini)
    assert not GeminiImporter().can_import(claude)
