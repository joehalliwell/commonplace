"""Chat importers"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import mdformat
from pydantic import BaseModel, Field

from commonplace import logger
from commonplace._import._chatgpt import ChatGptImporter
from commonplace._import._claude import ClaudeImporter
from commonplace._import._gemini import GeminiImporter
from commonplace._import._types import ActivityLog, Importer, Role
from commonplace._repo import Commonplace
from commonplace._types import Note
from commonplace._utils import slugify

IMPORTERS: list[Importer] = [GeminiImporter(), ClaudeImporter(), ChatGptImporter()]


class MarkdownSerializer(BaseModel):
    """
    A Markdown serializer for ActivityLog objects.

    Converts ActivityLog objects into formatted markdown files with
    frontmatter metadata, headers for each speaker, and proper
    timestamp annotations.
    """

    human: str = Field(default="Human", description="Name to use for the human interlocutor")
    assistant: str = Field(default="Assistant", description="Name to use for the AI assistant")
    timespec: str = Field(default="seconds", description="Timespec for isoformat used in titles")
    wrap: int = Field(default=80, description="Target characters per line for text wrapping")

    def serialize(self, log: ActivityLog, include_frontmatter=True) -> str:
        """
        Serializes an ActivityLog object to a Markdown string.
        """

        lines: list[str] = []
        if include_frontmatter:
            self._add_metadata(lines, log.metadata)

        title = log.title or "Conversation"
        self._add_header(
            lines,
            title,
            created=log.created.isoformat(timespec=self.timespec),
        )

        for message in log.messages:
            sender = self.human if message.sender == Role.USER else self.assistant

            self._add_header(
                lines,
                sender,
                level=2,
                created=message.created.isoformat(timespec=self.timespec),
            )
            self._add_metadata(lines, message.metadata, frontmatter=False)

            lines.append(message.content)
            lines.append("")

        markdown = "\n".join(lines)
        formatted = mdformat.text(
            markdown,
            extensions=[
                "frontmatter",
                "gfm",
            ],  # TODO: Check these can be enabled!
            options={"wrap": self.wrap, "number": True, "validate": True},
        )
        return formatted

    def _add_metadata(self, lines: list[str], metadata: dict[str, Any], frontmatter: bool = True) -> None:
        if not metadata:
            return
        start, end = ("---", "---") if frontmatter else ("```yaml", "```")
        lines.append(start)
        for k, v in metadata.items():
            lines.append(f"{k}: {v}")
        lines.append(end)
        lines.append("")

    def _add_header(self, lines: list[str], text: str, level: int = 1, **kwargs) -> None:
        bits = [
            "#" * level,
            text,
            *[f"[{k}:: {v}]" for k, v in kwargs.items()],
        ]
        lines.append(" ".join(bits))
        lines.append("")


def import_path(source: str, date: datetime, title: Optional[str], prefix="chats") -> Path:
    """
    Generate the relative file path for storing an activity log.

    Args:
        source: The source system (e.g., 'claude', 'gemini')
        date: The creation date of the log
        title: Optional title to include in filename

    Returns:
        Path where the log should be stored
    """
    slug = ""
    if title:
        slug = "-" + slugify(title)
    return (
        Path(prefix)
        / source
        / f"{date.year:02}"
        / f"{date.month:02}"
        / f"{date.year:02}-{date.month:02}-{date.day:02}{slug}.md"
    )


def import_(path: Path, repo: Commonplace, user: str, prefix="chats"):
    """
    Import chats from a supported provider into the repository.
    """
    importer = next((importer for importer in IMPORTERS if importer.can_import(path)), None)
    if importer is None:
        logger.error(f"The file {path} is not supported by any available importer")
        return
    logger.info(f"Using {importer} importer for {path}")
    serializer = MarkdownSerializer(human=user, assistant=importer.source.title())

    for log in importer.import_(path):
        path = import_path(
            source=log.source,
            date=log.created,
            title=log.title,
        )

        note = Note(
            path=path,
            content=serializer.serialize(log),
            metadata=log.metadata,
        )
        repo.save(note)
        logger.info(f"Stored log '{log.title}' at '{path}'")

    repo.commit(f"Import from {path} using {importer.source} importer")
