"""
Core data types and interfaces for the commonplace package.

This module defines the fundamental data structures used throughout
the application for representing conversations, messages, and importers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from pydantic import BaseModel, Field

Metadata: TypeAlias = dict[str, Any]
Pathlike: TypeAlias = str | Path


@dataclass(frozen=True)
class RepoPath:
    """
    Immutable reference to a file at a specific git tree state.

    Invariants:
    - path is always relative to repository root
    - ref is a git tree SHA (not branch name)
    - instances are hashable and suitable as dict keys
    """

    path: Path  # Relative to repo root
    ref: str  # Git tree SHA

    def __post_init__(self):
        if self.path.is_absolute():
            raise ValueError(f"RepoPath must be relative: {self.path}")
        # Ensure path is a Path object, not string
        object.__setattr__(self, "path", Path(self.path))

    def __str__(self) -> str:
        return f"{self.ref[:8]}:{self.path}"


@dataclass
class Note:
    """Note content at a specific repository location."""

    repo_path: RepoPath
    content: str


class Link(BaseModel):
    parent: Note
    child: Note
    metadata: Metadata = Field(
        default_factory=dict,
        description="Metadata associated with this link",
    )


@dataclass
class RepoStats:
    num_notes: int
    total_size_bytes: int = 0
    providers: dict[str, int] = Field(default_factory=dict)  # Provider name -> note count
    oldest_timestamp: int = 0  # Unix timestamp
    newest_timestamp: int = 0  # Unix timestamp
