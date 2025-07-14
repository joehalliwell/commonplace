from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Role(Enum):
    """Enum representing the different roles in a conversation."""

    SYSTEM = auto()
    USER = auto()
    ASSISTANT = auto()


class Message(BaseModel):
    """
    Represents a single message or turn in a conversation.
    """

    sender: Role = Field(description="The name or role of the sender")
    content: str = Field(description="The content of the message in Markdown")
    created: datetime = Field(
        description="The timestamp of when the message was sent or created",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary for any other metadata associated with the message (e.g., model used, token count)",
    )


class ActivityLog(BaseModel):
    """
    Represents a log of activity, which may include one or more messages or
    interactions, imported from a single source file or session.
    """

    source: str = Field(description="Source of the log (e.g., 'Gemini', 'ChatGPT').")
    title: str = Field(description="A short title for the journal entry.")

    created: datetime = Field(description="The ISO 8601 timestamp of when the log was imported into commonplace.")
    messages: list[Message] = Field(description="A list of messages or entries that make up this activity log.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary for any other metadata associated with this log (e.g., model used, token count).",
    )


class Importer(ABC):
    """
    Abstract base class for importing activity logs from different AI chat providers.

    Each importer should be able to:
    1. Determine if it can handle a given file format
    2. Parse the file and extract conversation data
    3. Convert the data into standardized ActivityLog objects
    """

    source: str = Field(description="The name of the source, e.g., 'Gemini', 'ChatGPT'.")

    @abstractmethod
    def can_import(self, path: Path) -> bool:
        """
        Check if the importer can handle the given file path.

        Args:
            path: Path to the file to check

        Returns:
            True if this importer can handle the file, False otherwise
        """
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def import_(self, path: Path) -> list[ActivityLog]:
        """
        Import activity logs from the source file or session.

        Args:
            path: Path to the file to import from

        Returns:
            List of ActivityLog objects extracted from the file

        Raises:
            Exception: If the file cannot be parsed or imported
        """
        raise NotImplementedError("Subclasses must implement this method.")
