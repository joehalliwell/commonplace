"""Marginalia: what's been said about a note since, kept in a shadow tree beside it rather than in it.

A note's marginalia sit at its path under `.commonplace/marginalia/`. Notes owned by another system of record
are rewritten on every fetch, and primitives are immutable, so this is the one place to say anything about any note.
Frontmatter holds current state (`tags`); the body is a log of dated lines, appended to and never rewritten by tag
changes. A note is read with its marginalia as one document (`_document`), so a link in the body is the note's.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from commonplace._config import MARGINALIA
from commonplace._links import Target, UnresolvedNote, resolve, resolve_target
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
    if not path.exists():
        return Marginalia(note=note)
    metadata, body = load_frontmatter(path.read_text())
    version = metadata.get("marginalia", MARGINALIA_VERSION)
    if version > MARGINALIA_VERSION:
        raise ValueError(f"'{path}' is marginalia v{version}, newer than this release's v{MARGINALIA_VERSION}")
    return Marginalia(note=note, ref=metadata.get("ref"), tags=list(metadata.get("tags") or []), body=body)


def write_marginalia(repo: Commonplace, marginalia: Marginalia) -> None:
    """Save the marginalia for the repo's next commit."""
    metadata: dict = {"marginalia": MARGINALIA_VERSION}
    if marginalia.ref:
        metadata["ref"] = marginalia.ref
    metadata["tags"] = marginalia.tags
    repo.save(Note(RepoPath(marginalia_path(marginalia.note)), marginalia.body, metadata))


def tagged(root: Path, tag: str) -> set[Path]:
    """Every note whose marginalia carry `tag`."""
    return {note for note in annotated_notes(root) if tag in read_marginalia(root, note).tags}


def tag(repo: Commonplace, spec: str, tags: list[str]) -> list[Path]:
    """Tag the notes `spec` names, committing as the user; returns the notes."""
    return _retag(repo, spec, lambda marginalia: marginalia.tagged(*tags), f"Tag {spec}: {', '.join(tags)}")


def untag(repo: Commonplace, spec: str, tags: list[str]) -> list[Path]:
    """Remove tags from the notes `spec` names, committing as the user; returns the notes."""
    return _retag(repo, spec, lambda marginalia: marginalia.untagged(*tags), f"Untag {spec}: {', '.join(tags)}")


def notes_named(repo: Commonplace, spec: str) -> list[Path]:
    """The whole notes `spec` names; a span is refused, since marginalia speak for a whole note."""
    if "#" in spec:
        raise UnresolvedNote(f"'{spec}' names a span; marginalia belong to whole notes")
    return resolve(spec, list(repo.paths()))


def link(repo: Commonplace, from_spec: str, to_spec: str, why: str, on: date | None = None) -> Target:
    """Add a link from a whole note to a note or a span in one, committing as the user; returns the target."""
    files = list(repo.paths())
    if "#" in from_spec:
        raise UnresolvedNote(f"'{from_spec}' names a span; marginalia belong to whole notes")
    source = resolve_target(from_spec, repo.root, files).note
    target = resolve_target(to_spec, repo.root, files)
    today = date.today()  # noqa: DTZ011 - the user's local day, as the journal's
    marginalia = read_marginalia(repo.root, source).linked(target, why, on or today)
    write_marginalia(repo, replace(marginalia, ref=repo.make_repo_path(source).ref))
    repo.commit(f"Link {from_spec} to {target}", auto_index=False, as_user=True)
    return target


def _retag(repo: Commonplace, spec: str, change: Callable[[Marginalia], Marginalia], message: str) -> list[Path]:
    notes = notes_named(repo, spec)
    for note in notes:
        marginalia = change(read_marginalia(repo.root, note))
        write_marginalia(repo, replace(marginalia, ref=repo.make_repo_path(note).ref))
    repo.commit(message, auto_index=False, as_user=True)
    return notes


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
