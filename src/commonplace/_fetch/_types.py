from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Fetcher(Protocol):
    """
    Protocol for capturing raw material directly from a provider.

    A Fetcher records what the provider sent and stops there: it writes a wire
    archive (see [[commonplace._wire]]) and interprets nothing. Interpreting it
    is the job of whatever is paired with it — an Importer for chats, a Mirror
    for live state. Each source therefore has both halves, and the seam between
    them is the archive on disk.
    """

    source: str

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        """Fetch new content.

        Args:
            destination: Directory to write the fetched artifact into.
            since: UTC cursor — only fetch what was updated after this
                instant. `None` means fetch everything. Compare parsed
                datetimes, not ISO strings, which mis-sort across offsets.

        Returns:
            Path to an importable file, or None if there is nothing worth
            importing. A mirrored source returns its listing even when nothing
            is new, since that is how a deletion is seen.
        """
        ...
