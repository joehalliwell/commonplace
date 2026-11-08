"""Marginalia: how the part of a note's node that's said about it since is stored, in a shadow tree beside it.

A note's marginalia sit at its path under `.commonplace/marginalia/`. Notes owned by another system of record
are rewritten on every fetch, and primitives are immutable, so this is the one place to say anything about any note.
Frontmatter holds current state (`tags`, labels on the node); the body is the node's second body, a log of dated
lines appended to and never rewritten by tag changes. `_graph` reads them as part of the node.
"""

from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from commonplace._config import MARGINALIA
from commonplace._links import Target
from commonplace._repo import Commonplace
from commonplace._types import Note, RepoPath
from commonplace._utils import load_frontmatter

#: The marginalia format this release writes. Bump it, with an example in tests/resources/marginalia/, on any change.
MARGINALIA_VERSION = 1


@dataclass(frozen=True)
class Marginalia:
    """One note's marginalia: its tags, and the log of what's been said about it."""

    note: Path  # The annotated note, relative to the root
    ref: str | None = None  # The commit that last changed the note when it was last annotated
    tags: list[str] = field(default_factory=list)
    body: str = ""

    def tagged(self, *tags: str) -> "Marginalia":
        """These marginalia with `tags` added, after those they have, each once."""
        return replace(self, tags=list(dict.fromkeys([*self.tags, *tags])))

    def untagged(self, *tags: str) -> "Marginalia":
        """These marginalia without `tags`."""
        return replace(self, tags=[tag for tag in self.tags if tag not in tags])

    def linked(self, target: Target, why: str, on: date) -> "Marginalia":
        """These marginalia with a link to `target` appended as a dated line."""
        line = f"- {on.isoformat()} [[{target}]]" + (f" {why}" if why else "")
        body = self.body if not self.body or self.body.endswith("\n") else self.body + "\n"
        return replace(self, body=f"{body}{line}\n")


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
    return Marginalia(note=note, ref=metadata.get("ref"), tags=list(metadata.get("tags") or []), body=body)


def write_marginalia(repo: Commonplace, marginalia: Marginalia) -> None:
    """Save the marginalia for the repo's next commit."""
    metadata: dict = {"marginalia": MARGINALIA_VERSION}
    if marginalia.ref:
        metadata["ref"] = marginalia.ref
    metadata["tags"] = marginalia.tags
    repo.save(Note(RepoPath(marginalia_path(marginalia.note)), marginalia.body, metadata))


def check_marginalia(repo: Commonplace, check: bool) -> tuple[list[str], list[str]]:
    """Re-attach marginalia whose note moved, committing as the bot; report those whose note is gone."""
    present = set(repo.paths())
    actions, gone = [], []
    for note in annotated_notes(repo.root):
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


def annotated_notes(root: Path) -> list[Path]:
    """The path of every note that has marginalia, in order, whether or not the note is still there."""
    shadow = root / MARGINALIA
    return sorted(path.relative_to(shadow) for path in shadow.rglob("*.md"))
