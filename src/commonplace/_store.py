from datetime import datetime
from pathlib import Path
from typing import Optional

import mdformat
from pydantic import BaseModel, Field

from commonplace import LOGGER
from commonplace._types import ActivityLog, Role
from commonplace._utils import slugify


class JSONSerializer(BaseModel):
    """
    A simple JSON serializer for ActivityLog objects.

    TODO: Add more human-readable markdown option as described in docs/import-format.md
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
    A simple Markdown serializer for ActivityLog objects.
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

    def _add_metadata(self, lines: list[str], metadata: dict, frontmatter=True):
        if not metadata:
            return
        start, end = ("---", "---") if frontmatter else ("```yaml", "```")
        lines.append(start)
        for k, v in metadata.items():
            lines.append(f"{k}: {v}")
        lines.append(end)
        lines.append("")

    def _add_header(self, lines: list[str], text, level: int = 1, **kwargs):
        bits = [
            "#" * level,
            text,
            *[f"[{k}:: {v}]" for k, v in kwargs.items()],
        ]
        lines.append(" ".join(bits))
        lines.append("")


class ActivityLogDirectoryStore(BaseModel):
    """
    Abstract base class for activity log stores.
    """

    root: Path = Field(description="Root directory for the activity log store.")
    serializer: MarkdownSerializer = MarkdownSerializer()

    def path(self, source: str, date: datetime, title: Optional[str]) -> Path:
        """
        Returns the last part of the path to the source file or log.
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
        Writes the activity log to the store.
        """
        path = self.path(log.source, log.created, log.title)
        path.parent.mkdir(parents=True, exist_ok=True)
        LOGGER.debug(f"Writing log to {path}")
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
        Returns a list of activity logs in the specified date range. Unusually
        end is inclusive. If no logs are found, returns an empty list.
        """
        logs = []
        for source_dir in self.root.iterdir():
            if not source_dir.is_dir():
                continue
            if sources is not None and source_dir not in sources:
                LOGGER.info(f"Skipping source {source_dir} not in {sources}")
                continue
            for log_file in source_dir.glob("*.md"):
                log_date = datetime.strptime(log_file.stem[:8], "%Y%m%d")
                if start <= log_date <= end:
                    logs.append(self._fetch(log_file))
        LOGGER.info(f"Fetched {len(logs)} logs from {self.root} between {start} and {end}")
        return logs
