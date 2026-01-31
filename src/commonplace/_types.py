"""
Core data types and interfaces for the commonplace package.

This module defines the fundamental data structures used throughout
the application for representing conversations, messages, and importers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

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
        return f"{self.path}@{self.ref[:8]}"


@dataclass
class Note:
    """Note content at a specific repository location."""

    repo_path: RepoPath
    content: str
