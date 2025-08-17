"""
Core data types and interfaces for the commonplace package.

This module defines the fundamental data structures used throughout
the application for representing conversations, messages, and importers.
"""

from pathlib import Path
from typing import Any, TypeAlias

from pydantic import BaseModel, Field

Metadata: TypeAlias = dict[str, Any]
Pathlike: TypeAlias = str | Path


class Note(BaseModel):
    path: Path
    content: str
    metadata: Metadata = Field(
        default_factory=dict,
        description="Metadata associated with this note",
    )


class Link(BaseModel):
    parent: Note
    child: Note
    metadata: Metadata = Field(
        default_factory=dict,
        description="Metadata associated with this link",
    )
