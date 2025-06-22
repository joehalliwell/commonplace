import json
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile

from rich.progress import track

from commonplace import LOGGER
from commonplace._types import ActivityLog, Importer, Message, Role
from commonplace._utils import truncate


class ClaudeImporter(Importer):
    """
    Importer for Claude activity logs.
    """

    source: str = "claude"

    def can_import(self, path: Path) -> bool:
        """Check if the importer can handle the given file path.

        For Claude, we can check if the file has a specific extension or contains
        certain metadata that indicates it's a Claude log.
        """
        try:
            with closing(ZipFile(path, "r")) as zip_file:
                files = zip_file.namelist()
                return "conversations.json" in files and "users.json" in files

        except Exception as e:
            LOGGER.info(
                f"{path} failed Gemini importability check: {e}",
                exc_info=True,
            )
            return False

    def import_(self, path: Path) -> list[ActivityLog]:
        """
        Import activity logs from the Claude file.
        """
        with closing(ZipFile(path)) as zf:
            threads = json.loads(zf.read("conversations.json"))
            # users = json.loads(zf.read("users.json"))
        return [self._to_log(thread) for thread in track(threads)]

    def _to_log(self, thread: dict) -> ActivityLog:
        """
        Convert a thread dictionary to an ActivityLog object.
        """
        title = thread["name"]
        created = thread["created_at"]
        messages = [self._to_message(msg) for msg in thread["chat_messages"]]

        return ActivityLog(
            source=self.source,
            created=created,
            messages=messages,
            title=title,
            metadata={"uuid": thread["uuid"]},
        )

    def _to_message(self, message: dict) -> Message:
        sender = Role.USER if message["sender"] == "human" else Role.ASSISTANT
        contents = message["content"]
        created = message["created_at"]
        lines = []
        for content in contents:
            type_ = content["type"]
            if type_ == "text":
                lines.append(content["text"])
            else:
                LOGGER.debug(f"Skipping {type_} content block {truncate(str(content))}")
                lines.extend(["> [!NOTE]", f"> Skipped content of type {type_}"])

        text = "\n".join(lines)
        return Message(sender=sender, content=text, created=created)
