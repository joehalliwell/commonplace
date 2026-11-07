import re
from typing import Any

import mdformat
from pydantic import BaseModel, Field

from commonplace._import._types import EventLog, Message, Role

# An unclosed artifact runs to the end of its message.
_ARTIFACT = re.compile(r"(?P<open><antArtifact\b[^>]*>)\n(?P<body>.*?)\n?(?:(?P<close></antArtifact>)|\Z)", re.DOTALL)
_LANGUAGE = re.compile(r'language="([^"]*)"')


def _fence_artifacts(content: str) -> str:
    """Fence artifact bodies that are not themselves markdown, so mdformat leaves them alone."""

    def fence(match: re.Match[str]) -> str:
        opening, body = match.group("open"), match.group("body")
        if 'type="text/markdown"' in opening:
            return match.group()
        language = language_match.group(1) if (language_match := _LANGUAGE.search(opening)) else ""
        return f"{opening}\n\n{_fenced(body, language)}\n\n{match.group('close') or ''}"

    return _ARTIFACT.sub(fence, content)


def _fenced(body: str, language: str = "") -> str:
    """`body` in a code fence long enough to survive any fences of its own."""
    ticks = "`" * max(3, *(len(run) + 1 for run in re.findall(r"`+", body)), 3)
    return f"{ticks}{language}\n{body}\n{ticks}"


class MarkdownSerializer(BaseModel):
    """
    A Markdown serializer for ActivityLog objects.

    Converts ActivityLog objects into formatted markdown files with
    frontmatter metadata, headers for each speaker, and proper
    timestamp annotations.
    """

    human: str = Field(default="Human", description="Name to use for the human interlocutor")
    agent: str = Field(default="Agent", description="Name to use for the AI agent")
    timespec: str = Field(default="seconds", description="Timespec for isoformat used in titles")
    wrap: int = Field(default=80, description="Target characters per line for text wrapping")

    def serialize(self, log: EventLog) -> str:
        """
        Serializes an ActivityLog object to the Markdown body of a note.
        """

        lines: list[str] = []
        title = log.title or "Conversation"
        self._add_header(
            lines,
            title,
            created=log.created.isoformat(timespec=self.timespec),
        )

        for event in log.events:
            if isinstance(event, Message):
                sender = {Role.USER: self.human, Role.AGENT: self.agent, Role.SYSTEM: "System"}[event.sender]

                self._add_header(
                    lines,
                    sender,
                    level=2,
                    created=event.created.isoformat(timespec=self.timespec),
                )
                self._add_metadata(lines, event.metadata)

                # Harness text is quoted, not composed: its headings must not join the note's outline.
                if event.sender == Role.SYSTEM:
                    lines.append(_fenced(event.content, "text"))
                else:
                    lines.append(_fence_artifacts(event.content))
                lines.append("")

        markdown = "\n".join(lines)
        return mdformat.text(
            markdown,
            extensions=["gfm"],
            options={"wrap": self.wrap, "number": True, "validate": True},
        )

    def _add_metadata(self, lines: list[str], metadata: dict[str, Any]) -> None:
        if not metadata:
            return
        lines.append("```yaml")
        for k, v in metadata.items():
            lines.append(f"{k}: {v}")
        lines.append("```")
        lines.append("")

    def _add_header(self, lines: list[str], text: str, level: int = 1, **kwargs) -> None:
        bits = [
            "#" * level,
            text,
            *[f"[{k}:: {v}]" for k, v in kwargs.items()],
        ]
        lines.append(" ".join(bits))
        lines.append("")
