"""What `init` lays down, and how `doctor` keeps an existing repo level with it.

The scaffold is `resources/scaffold/` as it lands in a repo; its dotfiles match nothing there, so they are inert.
A few files are seeded once and then the user's; the rest are commonplace's, so `doctor` prints their drift as a
diff and lets the reader decide: no merging, no rewriting, no guessing which side is right.
"""

import difflib
from pathlib import Path

from commonplace._config import CONFIG

_ROOT = Path(__file__).parent / "resources" / "scaffold"

# Seeded once and then the user's.
_USER_OWNED = frozenset({CONFIG.as_posix(), "index.md"})

#: Each scaffold file's path in a repo, with the template written there.
TEMPLATES = {
    file.relative_to(_ROOT).as_posix(): file.read_text() for file in sorted(_ROOT.rglob("*")) if file.is_file()
}


def install(root: Path, check: bool = False) -> list[str]:
    """The scaffolding missing from `root`, written there unless `check`."""
    missing = [path for path in TEMPLATES if not (root / path).exists()]
    if not check:
        for path in missing:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(TEMPLATES[path])
    return missing


def diff(root: Path) -> dict[str, list[str]]:
    """The diff, by path, of each file commonplace maintains that is present but behind its template."""
    found = {}
    for path, template in TEMPLATES.items():
        if path not in _USER_OWNED and (root / path).exists():
            existing = (root / path).read_text().splitlines()
            if lines := list(difflib.unified_diff(template.splitlines(), existing, "template", path, lineterm="")):
                found[path] = lines
    return found
