"""Every source commonplace captures from: each a node of the graph that owns its importers, its fetcher and its tree.

Order is behaviour. A capture goes to the first importer that claims it, a mirror's before a chat's, so of two
sources whose formats one importer could read, the narrower sorts first; and fetching runs in this order.
"""

from pathlib import Path
from typing import Any

from commonplace._fetch._chatgpt import ChatGptFetcher
from commonplace._fetch._chatgpt_memory import ChatGptMemoryFetcher
from commonplace._fetch._claude import ClaudeFetcher
from commonplace._fetch._claude_code import ClaudeCodeFetcher, ClaudeCodeMemoryFetcher
from commonplace._fetch._claude_memory import ClaudeMemoryFetcher
from commonplace._fetch._claude_tasks import ClaudeTasksFetcher
from commonplace._fetch._gemini import GeminiFetcher
from commonplace._fetch._gemini_memory import GeminiMemoryFetcher
from commonplace._fetch._keep import KeepFetcher
from commonplace._import._chatgpt import ChatGptImporter, ChatGptWireImporter
from commonplace._import._chatgpt_memory import ChatGptMemoryImporter
from commonplace._import._claude import ClaudeImporter
from commonplace._import._claude_code import ClaudeCodeImporter
from commonplace._import._claude_code_memory import ClaudeCodeMemoryImporter
from commonplace._import._claude_export import ClaudeExportImporter
from commonplace._import._claude_memory import ClaudeMemoryImporter
from commonplace._import._claude_tasks import ClaudeTasksImporter
from commonplace._import._gemini import GeminiImporter
from commonplace._import._gemini_memory import GeminiMemoryImporter
from commonplace._import._gemini_takeout import GeminiTakeoutImporter
from commonplace._import._keep import KeepImporter
from commonplace._types import ChatSource, MirrorSource, Source

SOURCES: tuple[Source, ...] = (
    MirrorSource("gemini-memory", Path("memory/gemini"), (GeminiMemoryImporter,), GeminiMemoryFetcher),
    MirrorSource("claude-memory", Path("memory/claude"), (ClaudeMemoryImporter,), ClaudeMemoryFetcher),
    MirrorSource(
        "claude-code-memory", Path("memory/claude-code"), (ClaudeCodeMemoryImporter,), ClaudeCodeMemoryFetcher
    ),
    MirrorSource("chatgpt-memory", Path("memory/chatgpt"), (ChatGptMemoryImporter,), ChatGptMemoryFetcher),
    MirrorSource("keep", Path("notes/keep"), (KeepImporter,), KeepFetcher),
    ChatSource("gemini-takeout", (GeminiTakeoutImporter,), None),
    ChatSource("gemini", (GeminiImporter,), GeminiFetcher),
    ChatSource("claude", (ClaudeExportImporter, ClaudeImporter), ClaudeFetcher),
    ChatSource("claude-tasks", (ClaudeTasksImporter,), ClaudeTasksFetcher),
    ChatSource("claude-code", (ClaudeCodeImporter,), ClaudeCodeFetcher),
    ChatSource("chatgpt", (ChatGptWireImporter, ChatGptImporter), ChatGptFetcher),
)

_BY_NAME = {source.name: source for source in SOURCES}


def source_named(name: str | None) -> Source | None:
    """The source called `name`, if commonplace knows one."""
    return _BY_NAME.get(name) if name else None


def importers(kind: type[Source]) -> list[Any]:
    """Every importer of a source of `kind`, in the order a capture is offered to them."""
    return [importer for source in SOURCES if isinstance(source, kind) for importer in source.importers]


def source_holding(path: Path) -> Source | None:
    """The source whose tree holds `path`, if any."""
    return next((source for source in SOURCES if path.is_relative_to(source.tree)), None)
