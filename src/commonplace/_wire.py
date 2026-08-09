"""The on-disk format for the wire archives fetchers produce.

A wire archive is the *primitive* artefact of a fetch: captured, not produced
(MANIFESTO §3.2), and the point at which provenance bottoms out (§3.5). It is
evidence of what a provider sent, so the pipeline splits in two — fetchers
record bytes and nothing else; importers do every interpretation. Anything a
fetcher decides is a decision no later reader can revisit.

Gzipped JSONL. First line is a header naming the provider, the format version,
and when the capture was written; every line after it records one exchange,
whose `response` is the verbatim body text:

    {"wire": "claude", "version": 3, "fetched_at": "...", "fetched_by": "commonplace/0.0.5.post46+g6b1d577"}
    {"endpoint": "conversations", "response": "[...]"}
    {"endpoint": "conversation", "cid": "...", "response": "{...}"}

Verbatim is load-bearing: parsing and re-serialising rewrites `1e5` as
`100000.0` and `\\/` as `/`, and resolves `\\u` escapes. Gzip costs no
inspection convenience — the content is opaque JSON either way — and saves
~7× on disk and LFS bandwidth.

Version 1 is the pre-versioning format: no header, and for Claude a `response`
already parsed. Those archives are committed in users' repos and referenced
from note frontmatter, so readers still accept them. Beyond the header, entry
shape is the provider's business: a version means the same thing to every
fetcher, but what changed at each version does not.

Version 3 adds `fetched_at` and `fetched_by`: when the capture was made, and
by what. Both were previously recoverable only from the commit that landed
the archive, which dates the landing rather than the capture and is lost
outright once the blob is detached from its history — and these archives are
built to be detached, stored content-addressed under `.commonplace/blobs/`
and referenced from frontmatter. Provenance that makes you leave the artefact
to date it does not bottom out there (§3.5).

`fetched_by` is not `version`. That one versions the container and tells a
reader how to parse the file; this one names the apparatus that did the
capturing, and the two drift independently. A fetcher bug — a dropped page, a
block the endpoint stopped returning — changes what got captured while the
format stays put, so `version` cannot answer "which archives came from the
build that was wrong?".

It names the implementation as well as its version, User-Agent style, because
nothing says this format has only one writer: a reimplementation records its
own token there and a reader holding archives from both can still tell them
apart. The version half is versioningit's, so a source install carries the
commit it was built from and a dirty marker
(`commonplace/0.0.5.post46+g6b1d577.d20260809`) rather than a bare release
number — which is what makes the field worth having, since fetchers are
usually run from a working tree. `0.0.0+dev` means the package metadata was
missing entirely.

Reading both is best-effort: v1 and v2 archives predate them, so they are
`None` for those.
"""

import gzip
import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from commonplace import __version__
from commonplace._utils import sniff_gzipped_jsonl

WIRE_VERSION = 3

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


def write_archive(path: Path, source: str, entries: Iterable[dict[str, Any]]) -> Path:
    """Write `entries` to `path` as a gzipped JSONL archive with a header."""
    header = {
        "wire": source,
        "version": WIRE_VERSION,
        "fetched_at": datetime.now(UTC).isoformat(),
        "fetched_by": f"{TOOL}/{__version__}",
    }
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def read_header(path: Path) -> WireHeader:
    """What the archive declares about itself.

    Returns `WireHeader(None, LEGACY_VERSION)` if `path` has no header —
    either a pre-versioning archive or a file that isn't a wire archive at
    all. Importers distinguish the two by their own legacy sniff.
    """
    entry = sniff_gzipped_jsonl(path)
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
    with gzip.open(path, "rt", encoding="utf-8") as f:
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
