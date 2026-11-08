"""Marginalia: how what's been said about a note since is stored, in a shadow tree beside it.

A note's marginalia sit at its path under `.commonplace/marginalia/`. Notes owned by another system of record
are rewritten on every fetch, and primitives are immutable, so this is the one place to say anything about any note.
Frontmatter holds current state (`tags`, labels on the node); the body is the node's second body, a log of dated
lines appended to and never rewritten by tag changes. `Commonplace.load` reads them into the note.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from commonplace._config import MARGINALIA
from commonplace._links import Target, UnresolvedNote
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


def notes_named(repo: "Commonplace", spec: str) -> list[Path]:
    """The whole notes `spec` names; a span is refused, since marginalia speak for a whole note."""
    return repo.files.resolve(_whole(spec))


def tag(repo: "Commonplace", spec: str, tags: list[str]) -> list[Path]:
    """Label the notes `spec` names in their marginalia, committing as the user; returns the notes."""
    return _annotate(repo, notes_named(repo, spec), lambda m: m.tagged(*tags), f"Tag {spec}: {', '.join(tags)}")


def untag(repo: "Commonplace", spec: str, tags: list[str]) -> list[Path]:
    """Remove labels from the marginalia of the notes `spec` names, committing as the user; returns the notes."""
    return _annotate(repo, notes_named(repo, spec), lambda m: m.untagged(*tags), f"Untag {spec}: {', '.join(tags)}")


def link(repo: "Commonplace", from_spec: str, to_spec: str, why: str, on: date | None = None) -> Target:
    """Add an edge from a whole note to a note or a span in one, in its marginalia, committing as the user."""
    source, target = repo.files.resolve_target(_whole(from_spec)).note, repo.files.resolve_target(to_spec)
    on = on or date.today()  # noqa: DTZ011 - the user's local day, as the journal's
    _annotate(repo, [source], lambda m: m.linked(target, why, on), f"Link {from_spec} to {target}")
    return target


def unlink(repo: "Commonplace", from_spec: str, to_spec: str) -> int:
    """Remove a note's edges to exactly `to_spec`'s target from its marginalia, committing as the user."""
    note = repo.load(RepoPath(repo.files.resolve_target(from_spec).note))
    try:
        target = str(repo.files.resolve_target(to_spec))
    except UnresolvedNote as e:
        # An edge whose note is gone can't be named any more, so take it as the marginalia write it.
        target = to_spec.removeprefix("[[").removesuffix("]]")
        if target not in [said.link.target for said in note.said]:
            dead = [said.link.target for said in note.said if not repo.files.lands(said)]
            hint = f"; a link whose note is gone is removed as written: {', '.join(dead)}" if dead else ""
            raise UnresolvedNote(f"{e}{hint}") from e
    marginalia, removed = note.unlinked(target)
    if not removed:
        raise ValueError(f"'{from_spec}' has no link to {target}")
    write_marginalia(repo, marginalia)
    repo.commit(f"Unlink {from_spec} from {target}", auto_index=False, as_user=True)
    return removed


def _annotate(
    repo: "Commonplace", notes: list[Path], change: Callable[[Marginalia], Marginalia], message: str
) -> list[Path]:
    """Rewrite the marginalia of `notes` by `change`, each at its note's commit, committing as the user."""
    for at in repo.repo_paths(notes):
        write_marginalia(repo, replace(change(read_marginalia(repo.root, at.path)), ref=at.ref))
    repo.commit(message, auto_index=False, as_user=True)
    return notes


def _whole(spec: str) -> str:
    """`spec`, unless it names a span, which marginalia can't speak for: they belong to whole notes."""
    if "#" in spec:
        raise UnresolvedNote(f"'{spec}' names a span; marginalia belong to whole notes")
    return spec


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
