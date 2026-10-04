from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Role(Enum):
    """Enum representing the different roles in a conversation."""

    SYSTEM = auto()
    USER = auto()
    ASSISTANT = auto()


class Event(BaseModel):
    created: datetime = Field(
        description="The timestamp of when the event occurred",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary for any other metadata associated with this event (e.g., model used, token count)",
    )


class Message(Event):
    """
    Represents a single message or turn in a conversation.
    """

    sender: Role = Field(description="The name or role of the sender")
    content: str = Field(description="The content of the message in Markdown")


class ToolCall(Event):
    tool: str = Field(description="The name of tool")
    args: dict[str, Any] = Field(description="The arguments to the tool call")
    output: str = Field(description="The output from the tool call")


class EventLog(BaseModel):
    """
    Represents a log of activity, which may include one or more messages or
    interactions, imported from a single source file or session.
    """

    source: str = Field(description="Source of the log (e.g., 'Gemini', 'ChatGPT')")
    title: str = Field(description="A short title for this conversation")
    events: Sequence[Event] = Field(description="A list of events in this log")
    created: datetime = Field(description="When this log was started")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary for any other metadata associated with this log (e.g., model used, token count)",
    )


@dataclass(frozen=True)
class Snapshot:
    """What one capture says about upstream state: the files it read, and every path that existed."""

    #: Frontmatter and body, as `load_frontmatter` returns them, by path relative to the importer's `tree`.
    files: dict[PurePosixPath, tuple[dict[str, Any], str]]
    #: The complete upstream listing, or `None` if the capture has none — in which case absence proves nothing.
    listed: set[PurePosixPath] | None


@runtime_checkable
class MemoryImporter(Protocol):
    """
    Protocol for mirroring live upstream state, where a ChatImporter accumulates closed conversations.

    Claimed exactly as a ChatImporter is, but what it yields is authoritative: files land at the
    paths the provider gave them, and paths missing from the listing are pruned.
    """

    source: str
    #: Where the files land, and so the fetch cursor's pathspec.
    tree: Path

    def can_import(self, path: Path) -> bool: ...

    def snapshot(self, path: Path) -> Snapshot: ...


@runtime_checkable
class ChatImporter(Protocol):
    """
    Protocol for importing activity logs from different AI chat providers.

    Each importer should be able to:
    1. Determine if it can handle a given file format
    2. Parse the file and extract conversation data
    3. Convert the data into standardized ActivityLog objects
    """

    source: str
    #: The one ZIP member `import_` reads, stored in place of the archive; `None` stores the file whole.
    member: str | None

    def can_import(self, path: Path) -> bool: ...

    def import_(self, path: Path) -> list[EventLog]: ...
