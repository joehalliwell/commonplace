"""
Core data types and interfaces for the commonplace package.

This module defines the fundamental data structures used throughout
the application for representing conversations, messages, and importers.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from commonplace._utils import override

#: A note's metadata, serialised as its frontmatter, which is where OKF's keys live.
type Metadata = dict[str, Any]
type Pathlike = str | Path


@dataclass(frozen=True)
class RepoPath:
    """
    Immutable reference to a note: its path, which corresponds to an OKF concept ID, at a version.

    Invariants:
    - path is always relative to repository root
    - ref is a git SHA (not branch name), or None for a note not yet committed
    - instances are hashable and suitable as dict keys
    """

    path: Path  # Relative to repo root
    ref: str | None = None

    def __post_init__(self):
        if self.path.is_absolute():
            raise ValueError(f"RepoPath must be relative: {self.path}")
        # Ensure path is a Path object, not string
        object.__setattr__(self, "path", Path(self.path))

    def __str__(self) -> str:
        return f"{self.path}@{self.ref[:8]}" if self.ref else str(self.path)


@dataclass
class Note:
    """A markdown file in the commonplace, of the kind its `type` names; it corresponds to an OKF concept document."""

    repo_path: RepoPath
    body: str
    metadata: Metadata = field(default_factory=dict)

    @classmethod
    def compose(cls, repo_path: RepoPath, type: str, title: str, body: str, metadata: Metadata | None = None) -> "Note":
        """A note whose `type` and `title` lead and override `metadata`."""
        return cls(repo_path, body, override(metadata or {}, repo_path, type=type, title=title))
