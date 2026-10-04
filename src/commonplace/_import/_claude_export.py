"""Importer for the manual Claude export ZIP (Settings → Privacy → Export data).

Structurally similar to [[ClaudeImporter]] — same per-thread parse — but the
archive layout is different: a ZIP containing `conversations.json` and
`users.json` (plus other files we ignore). Both importers write to
`chats/claude/` under the shared `source = "claude"` tag.

The manual export is worth keeping around because it preserves content the
internal API strips (notably `<antThinking>` blocks). See issue #6.
"""

import json
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile

from commonplace._import._claude import _to_log
from commonplace._import._types import EventLog
from commonplace._import._zip import head_contains, zip_contains
from commonplace._progress import track


class ClaudeExportImporter:
    source: str = "claude"
    name: str = "Claude"
    member: str | None = "conversations.json"

    def can_import(self, path: Path) -> bool:
        # A stored blob is a bare conversations.json: the ZIP was only packaging,
        # and the repo keeps the members, so the members have to be importable.
        # Bare, only content tells it from ChatGPT's same-named file: Claude says `chat_messages`, ChatGPT `mapping`.
        if path.suffix == ".json":
            return head_contains(path, '"chat_messages"')
        # `users.json` is the Claude-specific marker — distinguishes this
        # from ChatGPT ZIPs, which also contain `conversations.json`.
        return zip_contains(path, "conversations.json", "users.json")

    def import_(self, path: Path) -> list[EventLog]:
        if path.suffix == ".json":
            threads = json.loads(path.read_text(encoding="utf-8"))
        else:
            with closing(ZipFile(path)) as zf:
                threads = json.loads(zf.read("conversations.json"))
        return [_to_log(thread, self.source) for thread in track(threads)]
