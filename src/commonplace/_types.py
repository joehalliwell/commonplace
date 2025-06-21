from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class Role(Enum):
    SYSTEM = auto()
    USER = auto()
    ASSISTANT = auto()


class Message(BaseModel):
    """
    Represents a single message or turn in a conversation.
    """

    sender: Role = Field(description="The name or role of the sender.")
    content: str = Field(description="The content of the message, can be Markdown.")
    created: datetime = Field(
        description="The timestamp of when the message was sent or created.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary for any other metadata associated with the message (e.g., model used, token count).",
    )


class ActivityLog(BaseModel):
    """
    Represents a log of activity, which may include one or more messages or
    interactions, imported from a single source file or session.
    """

    source: str = Field(description="Source of the log (e.g., 'Gemini', 'ChatGPT').")
    title: str = Field(description="A short title for the journal entry.")

    created: datetime = Field(description="The ISO 8601 timestamp of when the log was imported into commonplace.")
    messages: List[Message] = Field(description="A list of messages or entries that make up this activity log.")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary for any other metadata associated with this log (e.g., model used, token count).",
    )


class Importer(ABC):
    source: str = Field(description="The name of the source, e.g., 'Gemini', 'ChatGPT'.")

    @abstractmethod
    def can_import(self, path: Path) -> bool:
        """
        Check if the importer can handle the given file path.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def import_(self, path: Path) -> List[ActivityLog]:
        """
        Import activity logs from the source file or session.
        Returns a list of ActivityLog objects.
        """
        raise NotImplementedError("Subclasses must implement this method.")
