"""Tests for the wire archive format shared by all fetchers."""

import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from commonplace import __version__
from commonplace._fetch._commands import default_fetchers
from commonplace._import._chatgpt import ChatGptWireImporter
from commonplace._import._claude import ClaudeImporter
from commonplace._import._commands import IMPORTERS, autodetect_importer
from commonplace._import._gemini import GeminiImporter
from commonplace._import._types import Importer
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


def _write_with_header(path: Path, header: dict, entries: list[dict]) -> Path:
    """An archive with a header we control — for spelling out older versions."""
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


def _header_line(archive: Path) -> dict:
    with gzip.open(archive, "rt", encoding="utf-8") as f:
        return json.loads(f.readline())


def test_write_archive_leads_with_a_header(tmp_path):
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    header = _header_line(archive)
    assert header["wire"] == "claude"
    assert header["version"] == WIRE_VERSION


def test_write_archive_records_when_it_was_written(tmp_path):
    """v3's guarantee: the capture dates itself, so a blob handed to someone
    without its commit is still datable (MANIFESTO §3.5)."""
    before = datetime.now(UTC)
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    after = datetime.now(UTC)

    fetched_at = datetime.fromisoformat(_header_line(archive)["fetched_at"])
    assert fetched_at.utcoffset() == timedelta(0), "must be UTC, not naive or local"
    assert before <= fetched_at <= after


def test_write_archive_records_the_capturing_version(tmp_path):
    """`version` is the container's; this is the apparatus's. A fetcher bug
    changes what got captured without changing the format, so the format
    version cannot answer "which archives came from the broken build?"."""
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    assert _header_line(archive)["commonplace_version"] == __version__


def test_read_header_returns_source_version_and_provenance(tmp_path):
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    header = read_header(archive)
    assert header.source == "claude"
    assert header.version == WIRE_VERSION
    assert header.fetched_at is not None
    assert header.fetched_at.utcoffset() == timedelta(0)
    assert header.commonplace_version == __version__


def test_read_header_treats_missing_header_as_legacy(tmp_path):
    archive = _write_legacy(tmp_path / "claude-wire.jsonl.gz", ENTRIES)
    header = read_header(archive)
    assert (header.source, header.version) == (None, LEGACY_VERSION)
    assert header.fetched_at is None


def test_read_header_tolerates_an_archive_written_before_v3(tmp_path):
    """v1 and v2 archives are committed in users' repos and referenced from
    note frontmatter, so an absent `fetched_at` is not an error."""
    archive = _write_with_header(tmp_path / "claude-wire.jsonl.gz", {"wire": "claude", "version": 2}, ENTRIES)
    header = read_header(archive)
    assert (header.source, header.version) == ("claude", 2)
    assert header.fetched_at is None
    assert header.commonplace_version is None


def test_read_header_on_unrelated_file(tmp_path):
    path = tmp_path / "other.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"not": "ours"}) + "\n")
    assert read_header(path) == (None, LEGACY_VERSION, None, None)


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


def test_an_importer_added_after_versioning_claims_no_headerless_archive(tmp_path):
    """Recognising a headerless archive means guessing from entry keys, which
    is exactly what the header exists to stop. ChatGPT arrived at v2, so every
    archive of its own has a header and anything headerless belongs to someone
    else — including files whose entry keys resemble its own."""
    claude = _write_legacy(tmp_path / "claude-wire.jsonl.gz", ENTRIES)
    gemini = _write_legacy(tmp_path / "gemini-wire.jsonl.gz", [{"rpc": "MaZiqc", "response": ""}])

    assert not ChatGptWireImporter().can_import(claude)
    assert not ChatGptWireImporter().can_import(gemini)


def test_wire_importers_extract_nothing(tmp_path):
    """A wire archive is gzipped JSONL, not a ZIP, so it is stored whole."""
    for importer in (ClaudeImporter(), GeminiImporter(), ChatGptWireImporter()):
        assert importer.required_paths() == []


# ---------------------------------------------------------------------------
# The seam itself: every fetcher's archive must reach its paired importer.
#
# `source` binds the two halves, but it is declared twice — once on the
# Fetcher, once on the Importer — and the registries carrying them
# (`default_fetchers()` and `IMPORTERS`) are maintained by hand, in different
# modules. A provider misspelt on one side, or an importer left out of
# `IMPORTERS`, fetches perfectly and imports nothing: the archive is written,
# no importer claims it, and the run reports no error. These tests are derived
# from the registries rather than from a list of their own, so a fourth
# provider is covered without anyone remembering to add it.
# ---------------------------------------------------------------------------


def _claims(importer: Importer, path: Path) -> bool:
    """`can_import` as `autodetect_importer` sees it — importers probing a
    format they don't handle are entitled to raise."""
    try:
        return importer.can_import(path)
    except Exception:  # noqa: BLE001 — mirrors autodetect_importer's own bare except
        return False


def _archive_for(fetcher, tmp_path: Path) -> Path:
    return write_archive(tmp_path / f"{fetcher.source}-wire.jsonl.gz", fetcher.source, ENTRIES)


def test_every_fetchers_archive_reaches_an_importer(tmp_path, test_repo):
    for fetcher in default_fetchers(test_repo.config):
        importer = autodetect_importer(_archive_for(fetcher, tmp_path))
        assert importer is not None, f"nothing in IMPORTERS claims a {fetcher.source!r} archive"
        assert importer.source == fetcher.source


def test_exactly_one_importer_claims_each_fetchers_archive(tmp_path, test_repo):
    """Two claimants would make the seam depend on `IMPORTERS` ordering, so
    reordering the list for an unrelated reason could silently reroute a
    provider."""
    for fetcher in default_fetchers(test_repo.config):
        archive = _archive_for(fetcher, tmp_path)
        claimants = [i.source for i in IMPORTERS if _claims(i, archive)]
        assert claimants == [fetcher.source]
