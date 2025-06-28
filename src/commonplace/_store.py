"""
Storage and serialization utilities for activity logs.

Provides classes for serializing ActivityLog objects to various formats
(JSON, Markdown) and storing them in organized directory structures.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Any

import mdformat
from pydantic import BaseModel, Field

from commonplace import logger
from commonplace._types import ActivityLog, Role
from commonplace._utils import slugify


class JSONSerializer(BaseModel):
    """
    A JSON serializer for ActivityLog objects.

    Provides methods to serialize ActivityLog objects to JSON strings
    and deserialize JSON strings back to ActivityLog objects.
    """

    indent: int = Field(default=2, description="Indentation level for JSON serialization")

    def serialize(self, log: ActivityLog) -> str:
        """
        Serializes an ActivityLog object to a JSON string.
        """
        return ActivityLog.model_dump_json(log, indent=self.indent)

    def deserialize(self, data: str) -> ActivityLog:
        """
        Deserializes a JSON string to an ActivityLog object.
        """
        return ActivityLog.model_validate_json(data)


class MarkdownSerializer(BaseModel):
    """
    A Markdown serializer for ActivityLog objects.

    Converts ActivityLog objects into formatted markdown files with
    frontmatter metadata, headers for each speaker, and proper
    timestamp annotations.
    """

    timespec: str = Field(default="seconds", description="Timespec for isoformat used in titles")
    human: str = Field(default="Human", description="Name to use for the human interlocutor")
    assistant: str = Field(default="Assistant", description="Name to use for the AI assistant")

    def serialize(self, log: ActivityLog) -> str:
        """
        Serializes an ActivityLog object to a Markdown string.
        """
        lines: list[str] = []
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
            self._add_metadata(lines, message.metadata)

            lines.append(message.content)
            lines.append("")

        markdown = "\n".join(lines)
        formatted = mdformat.text(
            markdown,
            extensions=[
                "frontmatter",
                "gfm",
            ],  # TODO: Check these can be enabled!
            options={"wrap": 80, "number": True, "validate": True},
        )
        return formatted

    def deserialize(self, data: str) -> ActivityLog:
        """
        Deserializes a Markdown string to an ActivityLog object.
        This is a placeholder as Markdown deserialization is not implemented.
        """
        raise NotImplementedError("Markdown deserialization is not implemented.")

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


class ActivityLogDirectoryStore(BaseModel):
    """
    A file-based store for activity logs organized by date and source.

    Stores logs in a directory structure like:
    root/source/YYYY/MM/YYYY-MM-DD-title-slug.md

    Each log is serialized to markdown format with frontmatter metadata.
    """

    root: Path = Field(description="Root directory for the activity log store.")
    serializer: MarkdownSerializer = MarkdownSerializer()

    def path(self, source: str, date: datetime, title: Optional[str]) -> Path:
        """
        Generate the file path for storing an activity log.

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
            self.root
            / source
            / f"{date.year:02}"
            / f"{date.month:02}"
            / f"{date.year:02}-{date.month:02}-{date.day:02}{slug}.md"
        )

    def store(self, log: ActivityLog) -> None:
        """
        Store an activity log to the filesystem.

        Args:
            log: The ActivityLog to store

        Raises:
            OSError: If there are filesystem permission or space issues
        """
        path = self.path(log.source, log.created, log.title)
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Writing log to {path}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.serializer.serialize(log))

    def _fetch(self, path: Path) -> ActivityLog:
        """
        Fetches an activity log from the store by source and date.
        """
        with open(path, "r", encoding="utf-8") as f:
            return self.serializer.deserialize(f.read())

    def fetch(
        self,
        start: datetime,
        end: datetime,
        sources: Optional[list[str]] = None,
    ) -> list[ActivityLog]:
        """
        Fetch activity logs within a date range.

        Args:
            start: Start date (inclusive)
            end: End date (inclusive)
            sources: Optional list of source names to filter by

        Returns:
            List of ActivityLog objects in the date range

        Note:
            Currently has implementation issues with deserialization.
        """
        logs = []
        for source_dir in self.root.iterdir():
            if not source_dir.is_dir():
                continue
            if sources is not None and source_dir.name not in sources:
                logger.info(f"Skipping source {source_dir} not in {sources}")
                continue
            for log_file in source_dir.glob("*.md"):
                log_date = datetime.strptime(log_file.stem[:8], "%Y%m%d")
                if start <= log_date <= end:
                    logs.append(self._fetch(log_file))
        logger.info(f"Fetched {len(logs)} logs from {self.root} between {start} and {end}")
        return logs
