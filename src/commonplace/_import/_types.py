from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from commonplace._types import Note


class Role(Enum):
    """Enum representing the different roles in a conversation."""

    SYSTEM = auto()
    USER = auto()
    AGENT = auto()


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


def models_field(names: Iterable[str | None]) -> dict[str, list[str]]:
    """The `models` frontmatter: each vendor-given name once, in order of first use; none known, no field."""
    distinct = list(dict.fromkeys(name for name in names if name))
    return {"models": distinct} if distinct else {}


@dataclass(frozen=True)
class Snapshot:
    """What one capture says about upstream state: the notes it read, and what else still exists."""

    #: Uncommitted notes, each at its path under the importer's `tree`.
    notes: list[Note]
    #: Paths upstream still has but the capture didn't read, or `None` without a listing — then absence proves nothing.
    unread: frozenset[Path] | None = frozenset()


class MemoryImporter(Protocol):
    """
    Protocol for mirroring live upstream state, where a ChatImporter accumulates closed conversations.

    Claimed exactly as a ChatImporter is, but what it yields is authoritative: files land at the
    paths the provider gave them, and paths missing from the listing are pruned.
    """

    source: str
    #: Where the files land, and so the fetch cursor's pathspec.
    tree: Path
    #: The frontmatter key holding a note's id, which keeps it at the path it first landed at rather than the
    #: one proposed now; for sources that name files after something that changes, like a note's title.
    #: `None`: upstream's own paths are authoritative.
    id_key: str | None

    def can_import(self, path: Path) -> bool: ...

    def snapshot(self, path: Path, earlier: Sequence[Path] = ()) -> Snapshot:
        """Upstream state as the capture at `path` shows it; `earlier` are the captures of this source already
        landed, oldest first, for an importer whose captures are changes on earlier ones; most ignore them."""
        ...


class ChatImporter(Protocol):
    """
    Protocol for importing activity logs from different AI chat providers.

    Each importer should be able to:
    1. Determine if it can handle a given file format
    2. Parse the file and extract conversation data
    3. Convert the data into standardized ActivityLog objects
    """

    source: str
    #: The agent's display name, which labels its turns; declared, since no key `.title()`s into "ChatGPT".
    name: str
    #: The one ZIP member `import_` reads, stored in place of the archive; `None` stores the file whole.
    member: str | None
    #: The metadata key holding the vendor's id for a conversation, which finds the path it already holds;
    #: `None` for logs with no id, which land where their date and title say.
    id_key: str | None

    def can_import(self, path: Path) -> bool: ...

    def import_(self, path: Path) -> list[EventLog]: ...
