from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Fetcher(Protocol):
    """
    Protocol for fetching raw export material directly from a provider.

    A Fetcher pulls source data into `destination` in whatever format the
    matching Importer already understands, so the existing import pipeline
    can consume it unchanged.
    """

    source: str

    def fetch(self, destination: Path, since: datetime | None) -> Path | None:
        """Fetch new content.

        Args:
            destination: Directory to write the fetched artifact into.
            since: UTC cursor — only fetch conversations updated after this
                instant. `None` means fetch everything. Compare parsed
                datetimes, not ISO strings, which mis-sort across offsets.

        Returns:
            Path to an importable file, or None if nothing new was fetched.
        """
        ...
