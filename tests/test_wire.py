"""Tests for the wire archive format shared by all fetchers."""

import gzip
import json
import lzma
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from commonplace import __version__
from commonplace._fetch._commands import default_fetchers
from commonplace._import._chatgpt import ChatGptWireImporter
from commonplace._import._claude import ClaudeImporter
from commonplace._import._commands import IMPORTERS, autodetect_importer, import_
from commonplace._import._gemini import GeminiImporter
from commonplace._wire import (
    LEGACY_VERSION,
    WIRE_VERSION,
    NewerWireVersion,
    archive_name,
    archive_names,
    entry_body,
    file_entry,
    read_entries,
    read_header,
    write_archive,
)

ENTRIES = [
    {"endpoint": "conversations", "response": "[]"},
    {"endpoint": "conversation", "cid": "abc", "response": "{}"},
]


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
    without its commit is still datable."""
    before = datetime.now(UTC)
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    after = datetime.now(UTC)

    fetched_at = datetime.fromisoformat(_header_line(archive)["fetched_at"])
    assert fetched_at.utcoffset() == timedelta(0), "must be UTC, not naive or local"
    assert before <= fetched_at <= after


def test_write_archive_records_what_captured_it(tmp_path):
    """`version` is the container's; this is the apparatus's. A fetcher bug
    changes what got captured without changing the format, so the format
    version cannot answer "which archives came from the broken build?"."""
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    assert _header_line(archive)["fetched_by"] == f"commonplace/{__version__}"


def test_fetched_by_names_the_implementation_not_just_its_version(tmp_path):
    """A reimplementation — a Rust port, say — writes its own token here, so a
    reader holding archives from both can tell which produced what. A bare
    version number could not distinguish them."""
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    fetched_by = read_header(archive).fetched_by
    assert fetched_by is not None
    tool, _, version = fetched_by.partition("/")
    assert tool == "commonplace"
    assert version == __version__


def test_read_header_returns_source_version_and_provenance(tmp_path):
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    header = read_header(archive)
    assert header.source == "claude"
    assert header.version == WIRE_VERSION
    assert header.fetched_at is not None
    assert header.fetched_at.utcoffset() == timedelta(0)
    assert header.fetched_by == f"commonplace/{__version__}"


def test_read_header_treats_missing_header_as_legacy(tmp_path, write_jsonl_gz):
    archive = write_jsonl_gz(tmp_path / "claude-wire.jsonl.gz", ENTRIES)
    header = read_header(archive)
    assert (header.source, header.version) == (None, LEGACY_VERSION)
    assert header.fetched_at is None


def test_read_header_tolerates_an_archive_written_before_v3(tmp_path, write_jsonl_gz):
    """v1 and v2 archives are committed in users' repos and referenced from
    note frontmatter, so an absent `fetched_at` is not an error."""
    archive = write_jsonl_gz(tmp_path / "claude-wire.jsonl.gz", [{"wire": "claude", "version": 2}, *ENTRIES])
    header = read_header(archive)
    assert (header.source, header.version) == ("claude", 2)
    assert header.fetched_at is None
    assert header.fetched_by is None


def test_read_header_on_unrelated_file(tmp_path, write_jsonl_gz):
    path = write_jsonl_gz(tmp_path / "other.jsonl.gz", [{"not": "ours"}])
    assert read_header(path) == (None, LEGACY_VERSION, None, None)


def test_read_entries_skips_the_header(tmp_path):
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    assert list(read_entries(archive)) == ENTRIES


def test_read_entries_yields_every_line_of_a_legacy_archive(tmp_path, write_jsonl_gz):
    archive = write_jsonl_gz(tmp_path / "claude-wire.jsonl.gz", ENTRIES)
    assert list(read_entries(archive)) == ENTRIES


def test_write_archive_preserves_non_ascii(tmp_path):
    entries = [{"endpoint": "conversation", "response": '{"name": "Café"}'}]
    archive = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", entries)
    assert list(read_entries(archive)) == entries


# ---------------------------------------------------------------------------
# Every version we have ever written, against the committed examples in
# tests/resources/wire/. `any_wire_version` is parametrised over the full
# range, so a bump without a matching example fails rather than going untested.
# ---------------------------------------------------------------------------


def test_every_wire_version_declares_its_own_version(any_wire_version):
    header = read_header(any_wire_version.path)
    assert header.version == any_wire_version.version
    # v1 predates the header, so its provider is not declared at all.
    assert header.source == (None if any_wire_version.version == LEGACY_VERSION else "claude")


def test_every_wire_version_is_claimed_by_the_claude_importer(any_wire_version):
    assert ClaudeImporter().can_import(any_wire_version.path)


def test_every_wire_version_imports_to_the_same_conversation(any_wire_version):
    """The back-compat guarantee itself. Old archives are committed in users'
    repos and referenced from note frontmatter, so a format change that
    quietly stopped reading one would corrupt history already written."""
    logs = ClaudeImporter().import_(any_wire_version.path)
    assert len(logs) == 1
    assert logs[0].metadata["uuid"] == "c-example"
    assert [e.content for e in logs[0].events] == ["hello", "hi back"]


def test_every_wire_version_records_the_conversation_models_in_order(any_wire_version):
    [log] = ClaudeImporter().import_(any_wire_version.path)
    assert log.metadata["models"] == ["claude-fable-5", "claude-opus-4-8", "claude-sonnet-4-6"]


def test_provenance_is_absent_before_v3_and_present_from_v3(any_wire_version):
    header = read_header(any_wire_version.path)
    if any_wire_version.version < 3:
        assert (header.fetched_at, header.fetched_by) == (None, None)
    else:
        assert header.fetched_at == datetime(2026, 8, 9, 12, tzinfo=UTC)
        assert header.fetched_by is not None and header.fetched_by.startswith("commonplace/")


def test_every_gemini_wire_version_imports_to_the_same_conversation(any_gemini_wire_version):
    """Bodies are Google's as fetched, redacted, so a fix for a new upstream shape must still read these."""
    assert GeminiImporter().can_import(any_gemini_wire_version.path)
    [log] = GeminiImporter().import_(any_gemini_wire_version.path)
    assert (log.metadata["uuid"], log.title, log.metadata["is_pinned"]) == ("c_60772b6269b693f9", "CHAT_TITLE_0", True)
    assert [e.content for e in log.events] == [
        "USER_TEXT_2",
        "MODEL_TEXT_2_0",
        "USER_TEXT_1",
        "MODEL_TEXT_1_0",
        "USER_TEXT_0",
        "MODEL_TEXT_0_0",
    ]


def test_importers_do_not_claim_each_others_archives(tmp_path):
    """The header makes provider identity declared rather than inferred from
    entry keys, which several providers would otherwise share."""
    claude = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", ENTRIES)
    gemini = write_archive(tmp_path / "gemini-wire.jsonl.gz", "gemini", [{"rpc": "MaZiqc", "response": ""}])

    assert ClaudeImporter().can_import(claude)
    assert not ClaudeImporter().can_import(gemini)
    assert GeminiImporter().can_import(gemini)
    assert not GeminiImporter().can_import(claude)


def test_importers_still_claim_legacy_archives(tmp_path, write_jsonl_gz):
    """Archives fetched before versioning are committed in users' repos."""
    claude = write_jsonl_gz(tmp_path / "claude-wire.jsonl.gz", ENTRIES)
    gemini = write_jsonl_gz(tmp_path / "gemini-wire.jsonl.gz", [{"rpc": "MaZiqc", "response": ""}])

    assert ClaudeImporter().can_import(claude)
    assert GeminiImporter().can_import(gemini)
    assert not ClaudeImporter().can_import(gemini)
    assert not GeminiImporter().can_import(claude)


def test_an_importer_added_after_versioning_claims_no_headerless_archive(tmp_path, write_jsonl_gz):
    """Recognising a headerless archive means guessing from entry keys, which
    is exactly what the header exists to stop. ChatGPT arrived at v2, so every
    archive of its own has a header and anything headerless belongs to someone
    else — including files whose entry keys resemble its own."""
    claude = write_jsonl_gz(tmp_path / "claude-wire.jsonl.gz", ENTRIES)
    gemini = write_jsonl_gz(tmp_path / "gemini-wire.jsonl.gz", [{"rpc": "MaZiqc", "response": ""}])

    assert not ChatGptWireImporter().can_import(claude)
    assert not ChatGptWireImporter().can_import(gemini)


@pytest.mark.parametrize("importer_class", [ClaudeImporter, GeminiImporter, ChatGptWireImporter])
def test_wire_importers_extract_nothing(importer_class):
    """A wire archive is gzipped JSONL, not a ZIP, so it is stored whole."""
    assert importer_class().member is None


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


def _archive_for(fetcher, tmp_path: Path) -> Path:
    return write_archive(tmp_path / f"{fetcher.source}-wire.jsonl.gz", fetcher.source, ENTRIES)


def test_every_fetchers_archive_reaches_an_importer(tmp_path, test_repo):
    reached = {}
    for fetcher in default_fetchers(test_repo.config):
        importer = autodetect_importer(_archive_for(fetcher, tmp_path))
        reached[fetcher.source] = importer and importer.source

    assert reached == {source: source for source in reached}


def test_exactly_one_importer_claims_each_fetchers_archive(tmp_path, test_repo, claims):
    """Two claimants would make the seam depend on `IMPORTERS` ordering, so
    reordering the list for an unrelated reason could silently reroute a
    provider."""
    claimants = {
        fetcher.source: [i.source for i in IMPORTERS if claims(i, _archive_for(fetcher, tmp_path))]
        for fetcher in default_fetchers(test_repo.config)
    }

    assert claimants == {source: [source] for source in claimants}


@pytest.mark.parametrize(
    "content",
    [b'{"type": "user"}\n', "café\r\nline two".encode(), b"\x89PNG\r\n\x1a\n\x00\xff"],
    ids=["json-text", "crlf-utf8", "binary"],
)
def test_file_entry_body_round_trips_the_bytes_through_an_archive(tmp_path, content):
    (tmp_path / "in.bin").write_bytes(content)
    archive = write_archive(tmp_path / "a.jsonl.gz", "test", [file_entry(tmp_path / "in.bin", "dir/in.bin")])

    [entry] = read_entries(archive)

    assert (entry["endpoint"], entry["path"], entry_body(entry)) == ("file", "dir/in.bin", content)


def test_file_entry_text_stays_readable_and_only_binary_is_encoded(tmp_path):
    (tmp_path / "text.md").write_bytes(b"# Notes\n")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\x00\xff")

    text, binary = file_entry(tmp_path / "text.md", "text.md"), file_entry(tmp_path / "image.png", "image.png")

    assert (text["response"], "encoding" in text) == ("# Notes\n", False)
    assert binary["encoding"] == "base64"


def test_archive_name_is_xz_and_lookups_also_find_gzip():
    """Archives stored before the switch keep their `.gz` names, and still belong to their source."""
    assert archive_name("claude") == "claude-wire.jsonl.xz"
    assert archive_names("claude") == ("claude-wire.jsonl.gz", "claude-wire.jsonl.xz")


def test_write_archive_compresses_with_xz(tmp_path):
    archive = write_archive(tmp_path / archive_name("test"), "test", ENTRIES)

    assert archive.read_bytes().startswith(b"\xfd7zXZ\x00")
    assert (read_header(archive).source, list(read_entries(archive))) == ("test", ENTRIES)


def test_a_gzip_and_an_xz_archive_of_the_same_capture_read_the_same(tmp_path):
    gzipped = write_archive(tmp_path / "test-wire.jsonl.gz", "test", ENTRIES)
    xz = tmp_path / archive_name("test")
    xz.write_bytes(lzma.compress(gzip.decompress(gzipped.read_bytes())))

    assert read_header(xz) == read_header(gzipped)
    assert list(read_entries(xz)) == list(read_entries(gzipped))


def _from_the_future(tmp_path: Path) -> Path:
    """An archive written by a commonplace newer than this one."""
    header = {"wire": "claude", "version": WIRE_VERSION + 1, "fetched_at": "2030-01-01T00:00:00+00:00"}
    path = tmp_path / archive_name("claude")
    path.write_bytes(lzma.compress((json.dumps(header) + "\n").encode()))
    return path


def test_read_header_refuses_an_archive_newer_than_it_reads(tmp_path):
    """Read as if it were the current version, a newer archive could be quietly misread."""
    with pytest.raises(NewerWireVersion, match="upgrade"):
        read_header(_from_the_future(tmp_path))


def test_import_of_a_newer_archive_fails_rather_than_being_skipped(tmp_path, test_repo):
    """Detection treats a file it can't read as not its own; a newer archive must not slip past that way."""
    with pytest.raises(NewerWireVersion):
        autodetect_importer(_from_the_future(tmp_path))
    with pytest.raises(NewerWireVersion):
        import_(_from_the_future(tmp_path), test_repo, user="Human", auto_index=False)
