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

    def fetch(self, destination: Path, since: str | None) -> Path | None:
        """Fetch new content.

        Args:
            destination: Directory to write the fetched artifact into.
            since: ISO 8601 cursor — only fetch conversations updated after
                this timestamp. `None` means fetch everything.

        Returns:
            Path to an importable file, or None if nothing new was fetched.
        """
        ...
