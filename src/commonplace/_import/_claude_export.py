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
from commonplace._progress import track

_SNIFF_BYTES = 1 << 20


def _is_claude_conversations(path: Path) -> bool:
    """True if this looks like Claude's conversations.json rather than ChatGPT's same-named file."""
    # Claude names a thread's messages `chat_messages`; ChatGPT uses `mapping`.
    # Co-location with users.json told us this inside a ZIP; on its own, only content can.
    with path.open(encoding="utf-8", errors="replace") as f:
        return '"chat_messages"' in f.read(_SNIFF_BYTES)


class ClaudeExportImporter:
    source: str = "claude"

    def required_paths(self) -> list[str]:
        # Both files get extracted and blob-stored so `source_exports`
        # captures the two primary artefacts from the export bundle.
        return ["conversations.json", "users.json"]

    def can_import(self, path: Path) -> bool:
        # A stored blob is a bare conversations.json: the ZIP was only packaging,
        # and the repo keeps the members, so the members have to be importable.
        if path.suffix == ".json":
            return _is_claude_conversations(path)
        if path.suffix != ".zip":
            return False
        try:
            with closing(ZipFile(path, "r")) as zf:
                names = zf.namelist()
        except Exception:  # noqa: BLE001 - probing an arbitrary file; any failure means "not ours"
            return False
        # `users.json` is the Claude-specific marker — distinguishes this
        # from ChatGPT ZIPs, which also contain `conversations.json`.
        return "conversations.json" in names and "users.json" in names

    def import_(self, path: Path) -> list[EventLog]:
        if path.suffix == ".json":
            threads = json.loads(path.read_text(encoding="utf-8"))
        else:
            with closing(ZipFile(path)) as zf:
                threads = json.loads(zf.read("conversations.json"))
        return [_to_log(thread, self.source) for thread in track(threads)]
