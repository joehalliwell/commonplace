from typing import Any

import mdformat
import yaml
from pydantic import BaseModel, Field

from commonplace._import._types import EventLog, Message, Role, ToolCall


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
    inline_tool_output: bool = Field(default=True, description="If true, tool output will be included in full")

    def serialize(self, log: EventLog, include_frontmatter=True) -> str:
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

        for event in log.events:
            if isinstance(event, Message):
                sender = self.human if event.sender == Role.USER else self.assistant

                self._add_header(
                    lines,
                    sender,
                    level=2,
                    created=event.created.isoformat(timespec=self.timespec),
                )
                self._add_metadata(lines, event.metadata, frontmatter=False)

                lines.append(event.content)
                lines.append("")

            elif isinstance(event, ToolCall):
                assert isinstance(event, ToolCall)
                self._add_header(
                    lines,
                    f"{event.tool} call",
                    level=2,
                    created=event.created.isoformat(timespec=self.timespec),
                )
                lines.append("")
                details = {
                    "tool": event.tool,
                    "args": event.args,
                }
                if self.inline_tool_output:
                    details["output"] = event.output
                yaml_str = yaml.dump(details, sort_keys=False)
                lines.append(f"```yaml\n{yaml_str}\n```")

        markdown = "\n".join(lines)
        formatted = mdformat.text(
            markdown,
            extensions=[
                "frontmatter",
                "gfm",
            ],
            options={"wrap": self.wrap, "number": True, "validate": True},
        )
        return formatted

    def _add_metadata(self, lines: list[str], metadata: dict[str, Any], frontmatter: bool = True) -> None:
        if not metadata:
            return
        start, end = ("---", "---") if frontmatter else ("```yaml", "```")
        lines.append(start)
        for k in metadata:
            lines.append(f"{k}: {metadata[k]}")
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
