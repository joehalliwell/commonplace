"""Shared plumbing for importers that consume a fetcher's wire archive.

The archive is the seam between a Fetcher and its paired Importer (see
[[commonplace._wire]]), and it names its own provider in the header. So
claiming one is the same operation for every provider: read the header,
compare. Only the headerless v1 case needs provider knowledge, and only for
providers that existed to write one.

[[commonplace._import._types.Importer]] remains the contract. Importers that
consume something other than a wire archive — export ZIPs, Takeout, Claude
Code — satisfy that Protocol directly and have no business here: they identify
themselves by archive contents, and several of them do declare
`required_paths`.
"""

from pathlib import Path

from commonplace._wire import read_header


class BaseWireImporter:
    """Recognises the wire archive written by the fetcher of the same `source`."""

    source: str

    def required_paths(self) -> list[str]:
        """Nothing to extract: a wire archive is gzipped JSONL, not a ZIP, so
        it is stored whole. True of every wire importer, not just a default."""
        return []

    def can_import(self, path: Path) -> bool:
        source, _ = read_header(path)
        if source is not None:
            return source == self.source
        return self._claims_legacy(path)

    def _claims_legacy(self, path: Path) -> bool:
        """Whether a headerless archive is ours.

        Defaults to no. An importer whose provider was added at wire version 2
        or later has no headerless archives in the wild to recognise, and
        guessing at one would mean claiming another provider's file — the
        entry keys alone are not distinctive enough, which is why the header
        exists. Providers that predate it override this."""
        return False
