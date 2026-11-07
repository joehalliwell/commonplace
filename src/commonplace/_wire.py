"""The on-disk format for the wire archives fetchers produce.

A wire archive is the *primitive* artefact of a fetch: captured, not produced
(MANIFESTO §3.2), and the point at which provenance bottoms out (§3.5). It is
evidence of what a provider sent, so the pipeline splits in two — fetchers
record bytes and nothing else; importers do every interpretation. Anything a
fetcher decides is a decision no later reader can revisit.

JSONL, xz-compressed (gzip before 0.8.0; readers tell them apart by their magic
bytes, so both still read). First line is a header naming the provider, the format version,
and when the capture was written; every line after it records one exchange,
whose `response` is the verbatim body text:

    {"wire": "claude", "version": 3, "fetched_at": "...", "fetched_by": "commonplace/0.0.5.post46+g6b1d577"}
    {"endpoint": "conversations", "response": "[...]"}
    {"endpoint": "conversation", "cid": "...", "response": "{...}"}

Verbatim is load-bearing: parsing and re-serialising rewrites `1e5` as
`100000.0` and `\\/` as `/`, and resolves `\\u` escapes. Compression costs no
inspection convenience — the content is opaque JSON either way (`xzcat`, not
`zcat`). xz is 1.7× smaller than gzip across a live corpus, 2.7× on Claude Code
transcripts, whose repeats lie further apart than gzip's 32 KB window reaches;
it compresses ~6× slower. Its price is git's delta packing: a re-capture of content an
earlier archive holds costs its full compressed size again, so history grows
with how often a source re-captures (for Claude Code sessions, ~1.3× the
minimum at a daily fetch, ~3.7× at hourly).

A body is text. One that isn't valid UTF-8, like an image a local fetcher read
off disk, is base64 in `response`, and the entry says so with
`"encoding": "base64"`, as HAR does. Base64 for every body would cost ~70%
more after compression, since it hides repeats from the compressor. Read a
body through `entry_body`, the one place that decodes it. A fetcher that reads
files records each with `file_entry`: `{"endpoint": "file", "path": ...}`.

Version 1 is the pre-versioning format: no header, and for Claude a `response`
already parsed. Those archives are committed in users' repos and referenced
from note frontmatter, so readers still accept them. Beyond the header, entry
shape is the provider's business: a version means the same thing to every
fetcher, but what changed at each version does not.

Version 3 adds `fetched_at` and `fetched_by`: when the capture was made and
what made it (`tool/version`), so a blob detached from its commit still dates
and attributes itself. Both read back `None` on v1 and v2 archives.

A vendor changing what it sends is not a version bump: bodies are verbatim, so
the format holds and only the content moves. Bump when a fetcher changes what
it records around the body. The importer then reads both shapes, telling them
apart by the body itself, never by `fetched_at`, which v1 and v2 lack. Commit
an example of the old shape before changing the importer, so the fix is shown
not to drop it.

`tests/resources/wire/` holds one example archive per version, per kind of
source (chat, memory) — the evidence of what each actually looked like. Add
one of each with the next version bump.
"""

import base64
import gzip
import json
import lzma
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, NamedTuple, cast

from commonplace import __version__

WIRE_VERSION = 3

GZ, XZ = ".jsonl.gz", ".jsonl.xz"
_XZ_MAGIC = b"\xfd7zXZ\x00"

# Archives written before the header existed.
LEGACY_VERSION = 1

#: Names this implementation in `fetched_by`. A reimplementation writes its
#: own token here; see the module docstring.
TOOL = "commonplace"


class WireHeader(NamedTuple):
    """What the archive says about itself."""

    #: Provider key, or `None` for a headerless archive.
    source: str | None
    version: int
    #: When `write_archive` wrote the file, or `None` before v3. This is the
    #: *end* of the capture, not an instant: a paced fetch of many
    #: conversations can span an hour before the archive is written.
    fetched_at: datetime | None = None
    #: What captured it, as `tool/version`, or `None` before v3. From a
    #: source tree the version pins the commit; see the module docstring.
    fetched_by: str | None = None


def write_archive(
    path: Path, source: str, entries: Iterable[dict[str, Any]], fetched_at: datetime | None = None
) -> Path:
    """Write `entries` to `path` as a compressed JSONL archive with a header stamped `fetched_at`, else now."""
    header = {
        "wire": source,
        "version": WIRE_VERSION,
        "fetched_at": (fetched_at or datetime.now(UTC)).isoformat(),
        "fetched_by": f"{TOOL}/{__version__}",
    }
    with _open(path, "wt") as f:
        f.write(json.dumps(header) + "\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def archive_name(source: str) -> str:
    """What a fetch of `source` names its archive."""
    return f"{source}-wire{XZ}"


def archive_names(source: str) -> tuple[str, ...]:
    """Every name an archive of `source` has had, oldest first: they were gzip before 0.8.0."""
    return (f"{source}-wire{GZ}", archive_name(source))


def _open(path: Path, mode: str) -> IO[str]:
    """`path` as text through its codec: written as its suffix says, read as its magic bytes say."""
    if mode.startswith("w"):
        xz = path.name.endswith(XZ)
    else:
        with path.open("rb") as raw:
            xz = raw.read(len(_XZ_MAGIC)) == _XZ_MAGIC
    opener = lzma.open if xz else gzip.open
    return cast(IO[str], opener(path, mode, encoding="utf-8"))


def _first_entry(path: Path) -> dict | None:
    """The first JSON object in a wire-named archive, or None for any other file."""
    if not path.name.endswith((GZ, XZ)):
        return None
    try:
        with _open(path, "rt") as f:
            entry = json.loads(f.readline())
    except Exception:  # noqa: BLE001 - probing an arbitrary file; any failure means "not ours"
        return None
    return entry if isinstance(entry, dict) else None


def read_header(path: Path) -> WireHeader:
    """What the archive declares about itself.

    Returns `WireHeader(None, LEGACY_VERSION)` if `path` has no header —
    either a pre-versioning archive or a file that isn't a wire archive at
    all. Importers distinguish the two by their own legacy sniff.
    """
    entry = _first_entry(path)
    if entry is None or "wire" not in entry:
        return WireHeader(None, LEGACY_VERSION)
    fetched_at = entry.get("fetched_at")
    return WireHeader(
        entry["wire"],
        entry["version"],
        datetime.fromisoformat(fetched_at) if fetched_at else None,
        entry.get("fetched_by"),
    )


def read_entries(path: Path) -> Iterator[dict[str, Any]]:
    """Yield the recorded exchanges, skipping the header if there is one."""
    with _open(path, "rt") as f:
        first = True
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if first:
                first = False
                if "wire" in entry:
                    continue
            yield entry


def file_entry(path: Path, name: str) -> dict[str, Any]:
    """The file at `path`, recorded as `name`: its exact bytes as text, or base64 when they aren't UTF-8."""
    content = path.read_bytes()
    try:
        return {"endpoint": "file", "path": name, "response": content.decode("utf-8")}
    except UnicodeDecodeError:
        return {"endpoint": "file", "path": name, "response": base64.b64encode(content).decode(), "encoding": "base64"}


def entry_body(entry: dict[str, Any]) -> bytes:
    """An entry's body as the bytes it was captured as, whatever it was encoded as to travel."""
    if entry.get("encoding") == "base64":
        return base64.b64decode(entry["response"])
    return entry["response"].encode("utf-8")
