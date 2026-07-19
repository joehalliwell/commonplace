from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from commonplace._repo import Commonplace


@runtime_checkable
class Fetcher(Protocol):
    """
    Protocol for fetching raw export material directly from a provider.

    A Fetcher pulls source data into `destination` in whatever format the
    matching Importer already understands, so the existing import pipeline
    can consume it unchanged.
    """

    source: str

    def fetch(self, destination: Path, repo: "Commonplace") -> Path | None:
        """Fetch new content.

        Args:
            destination: Directory to write the fetched artifact into.
            repo: The commonplace repository; used to derive the incremental
                cursor from git history so no cache file is needed.

        Returns:
            Path to an importable file, or None if nothing new was fetched.
        """
        ...
