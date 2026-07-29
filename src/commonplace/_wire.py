"""The on-disk format for the wire archives fetchers produce.

A wire archive is the *primitive* artefact of a fetch: captured, not produced
(MANIFESTO §3.2), and the point at which provenance bottoms out (§3.5). It is
evidence of what a provider sent, so the pipeline splits in two — fetchers
record bytes and nothing else; importers do every interpretation. Anything a
fetcher decides is a decision no later reader can revisit.

Gzipped JSONL. First line is a header naming the provider and format version;
every line after it records one exchange, whose `response` is the verbatim
body text:

    {"wire": "claude", "version": 2}
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
"""

import gzip
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from commonplace._utils import sniff_gzipped_jsonl

WIRE_VERSION = 2

# Archives written before the header existed.
LEGACY_VERSION = 1


def write_archive(path: Path, source: str, entries: Iterable[dict[str, Any]]) -> Path:
    """Write `entries` to `path` as a gzipped JSONL archive with a header."""
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"wire": source, "version": WIRE_VERSION}) + "\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def read_header(path: Path) -> tuple[str | None, int]:
    """The archive's `(provider, version)`.

    Returns `(None, LEGACY_VERSION)` if `path` has no header — either a
    pre-versioning archive or a file that isn't a wire archive at all.
    Importers distinguish the two by their own legacy sniff.
    """
    entry = sniff_gzipped_jsonl(path)
    if entry is None or "wire" not in entry:
        return None, LEGACY_VERSION
    return entry["wire"], entry["version"]


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
