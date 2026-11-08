"""Marginalia: how what's been said about a note since is stored, in a shadow tree beside it.

A note's marginalia sit at its path under `.commonplace/marginalia/`. Notes owned by another system of record
are rewritten on every fetch, and primitives are immutable, so this is the one place to say anything about any note.
Frontmatter holds current state (`tags`, labels on the node); the body is the node's second body, a log of dated
lines appended to and never rewritten by tag changes. `Commonplace.load` reads them into the note.
"""

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from commonplace._config import MARGINALIA
from commonplace._types import Marginalia, Note, RepoPath
from commonplace._utils import load_frontmatter

if TYPE_CHECKING:
    from commonplace._repo import Commonplace

#: The marginalia format this release writes. Bump it, with an example in tests/resources/marginalia/, on any change.
MARGINALIA_VERSION = 1


def marginalia_path(note: Path) -> Path:
    """Where a note's marginalia live, relative to the root."""
    return MARGINALIA / note


def read_marginalia(root: Path, note: Path) -> Marginalia:
    """The note's marginalia, empty if nothing has been said about it."""
    path = root / marginalia_path(note)
    return parse_marginalia(note, path.read_text()) if path.exists() else Marginalia(note=note)


def parse_marginalia(note: Path, text: str) -> Marginalia:
    """`note`'s marginalia, from the text of their file."""
    metadata, body = load_frontmatter(text)
    version = metadata.get("marginalia", MARGINALIA_VERSION)
    if version > MARGINALIA_VERSION:
        raise ValueError(f"The marginalia of '{note}' are v{version}, newer than this release's v{MARGINALIA_VERSION}")
    tags = list(metadata.get("tags") or [])
    return Marginalia(note, metadata.get("ref"), tags, body, offset=text.count("\n") - body.count("\n"))


def write_marginalia(repo: "Commonplace", marginalia: Marginalia) -> None:
    """Save the marginalia for the repo's next commit."""
    metadata: dict = {"marginalia": MARGINALIA_VERSION}
    if marginalia.ref:
        metadata["ref"] = marginalia.ref
    metadata["tags"] = marginalia.tags
    repo.save(Note(RepoPath(marginalia_path(marginalia.note)), marginalia.body, metadata))


def check_marginalia(repo: "Commonplace", check: bool) -> tuple[list[str], list[str]]:
    """Re-attach marginalia whose note moved, committing as the bot; report those whose note is gone."""
    present = set(repo.paths())
    actions, gone = [], []
    for note in repo.annotated():
        if note in present:
            continue
        marginalia = read_marginalia(repo.root, note)
        moved = repo.renamed_since(marginalia.ref).get(note) if marginalia.ref else None
        if moved is None or moved not in present or (repo.root / marginalia_path(moved)).exists():
            gone.append(f"  {note}")
            continue
        if check:
            actions.append(f"Would move the marginalia for {note} to {moved}")
            continue
        repo.remove(marginalia_path(note))
        write_marginalia(repo, replace(marginalia, note=moved, ref=repo.make_repo_path(moved).ref))
        actions.append(f"Moved the marginalia for {note} to {moved}")
    if actions and not check:
        repo.commit("Re-attach marginalia to moved notes", auto_index=False)

    warnings = (
        [f"Marginalia for {len(gone)} notes outlive them, kept as the record:\n" + "\n".join(gone)] if gone else []
    )
    return actions, warnings
