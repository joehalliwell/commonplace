from pathlib import Path

import pytest

from commonplace._sources import source_holding


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("chats/claude/2026/11/x.md", "claude"),
        ("chats/claude/tasks/2026/11/x.md", "claude"),
        ("chats/claude-code/2026/11/x.md", "claude-code"),
        ("chats/antigravity/2026/11/x.md", "antigravity"),
        ("notes/keep/2014/01/x.md", "keep"),
        ("notes/ideas.md", None),
        ("chats", None),
    ],
)
def test_source_holding_matches_whole_path_segments(path, name):
    source = source_holding(Path(path))

    assert (source and source.name) == name
