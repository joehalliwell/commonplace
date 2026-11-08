"""Marginalia: what's been said about a note since, kept in a shadow tree beside it rather than in it.

A note's marginalia sit at its path under `.commonplace/marginalia/`. Notes owned by another system of record
are rewritten on every fetch, and primitives are immutable, so this is the one place to say anything about any note.
Frontmatter holds current state (`tags`); the body is a log of dated lines, appended to and never rewritten by tag
changes. Every wikilink in the body is a link from the note.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass, field, replace
from datetime import date
from functools import cached_property
from pathlib import Path

from commonplace._config import MARGINALIA
from commonplace._links import (
    SKIPPED_ROOTS,
    Link,
    LinkKind,
    Target,
    UnresolvedNote,
    extract_links,
    lands,
    lands_on,
    resolve,
    resolve_target,
)
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

    @cached_property
    def wikilinks(self) -> list[Link]:
        """Every wikilink in the body, at its line in the body: each is a link from this note, prose or not."""
        found = extract_links(self.body, source=marginalia_path(self.note))
        return [link for link in found if link.kind is LinkKind.WIKILINK]

    @property
    def commentary(self) -> list[str]:
        """The body's lines that link nowhere: what's been said about the note, rather than what it's linked to."""
        linked = {link.line for link in self.wikilinks}
        return [line for n, line in enumerate(self.body.split("\n"), 1) if line.strip() and n not in linked]

    @property
    def links(self) -> list[str]:
        """Every wikilink target in the body, in order."""
        return [link.target for link in self.wikilinks]

    def line(self, link: Link) -> str:
        """The body line `link` is written on."""
        return self.body.split("\n")[link.line - 1]

    def linked(self, target: Target, why: str, on: date) -> "Marginalia":
        """These marginalia with a link to `target` appended as a dated line."""
        line = f"- {on.isoformat()} [[{target}]]" + (f" {why}" if why else "")
        body = self.body if not self.body or self.body.endswith("\n") else self.body + "\n"
        return replace(self, body=f"{body}{line}\n")

    def unlinked(self, target: Target | str) -> tuple["Marginalia", int]:
        """These marginalia without the body lines that link to exactly `target`, and how many went."""
        dropped = {link.line for link in self.wikilinks if link.target == str(target)}
        kept = [line for n, line in enumerate(self.body.split("\n"), 1) if n not in dropped]
        return replace(self, body="\n".join(kept)), len(dropped)


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


def unlink(repo: Commonplace, from_spec: str, to_spec: str) -> int:
    """Remove a note's links to exactly `to_spec`'s target, committing as the user; returns how many went."""
    files = list(repo.paths())
    source = resolve_target(from_spec, repo.root, files).note
    marginalia = read_marginalia(repo.root, source)
    target: Target | str
    try:
        target = resolve_target(to_spec, repo.root, files)
    except UnresolvedNote as e:
        # A link whose note is gone can't be named any more, so take it as the marginalia write it.
        written = to_spec.removeprefix("[[").removesuffix("]]")
        if written not in marginalia.links:
            dead = [found for found in marginalia.links if not _resolves(found, repo.root, files)]
            hint = f"; a link whose note is gone is removed as written: {', '.join(dead)}" if dead else ""
            raise UnresolvedNote(f"{e}{hint}") from e
        target = written
    marginalia, removed = marginalia.unlinked(target)
    if not removed:
        raise ValueError(f"'{from_spec}' has no link to {target}")
    write_marginalia(repo, marginalia)
    repo.commit(f"Unlink {from_spec} from {target}", auto_index=False, as_user=True)
    return removed


def _retag(repo: Commonplace, spec: str, change: Callable[[Marginalia], Marginalia], message: str) -> list[Path]:
    notes = notes_named(repo, spec)
    for note in notes:
        marginalia = change(read_marginalia(repo.root, note))
        write_marginalia(repo, replace(marginalia, ref=repo.make_repo_path(note).ref))
    repo.commit(message, auto_index=False, as_user=True)
    return notes


@dataclass(frozen=True)
class Neighbour:
    """A link to or from a note: the note at the other end, rooted, and where the link is written."""

    direction: str  # "out" from the note, or "in" to it
    other: str
    context: str  # The marginalia line, or "line N" of a note's own text


def links(
    repo: Commonplace, spec: str, include_hidden: bool = False, incoming: bool = True, outgoing: bool = True
) -> list[Neighbour]:
    """A note's links, out then in, from marginalia and from notes' own text; hidden notes at the other end left out."""
    [note] = notes_named(repo, spec)
    files = list(repo.paths())
    found = [
        *(links_from(repo.root, note, files) if outgoing else []),
        *(links_to(repo.root, note, files) if incoming else []),
    ]
    hidden = set() if include_hidden else tagged(repo.root, "hidden")
    return [neighbour for neighbour, other in found if other not in hidden]


def links_from(root: Path, note: Path, files: Collection[Path]) -> list[tuple[Neighbour, Path | None]]:
    """Every link from `note`, its marginalia's then its own text's, with the note at the other end if it has one."""
    # A marginalia link was written on purpose, so it shows landing or not; one in the note's text once it lands.
    notes, present = [path for path in files if path.suffix == ".md"], set(files)
    marginalia = read_marginalia(root, note)
    found: list[tuple[Neighbour, Path | None]] = [
        (Neighbour("out", written.target, marginalia.line(written)), lands(written, root, notes, present))
        for written in marginalia.wikilinks
    ]
    for written in extract_links((root / note).read_text(errors="replace"), source=note):
        if (other := lands(written, root, notes, present)) is not None:
            found.append((Neighbour("out", str(Target(other)), f"line {written.line}"), other))
    return found


def links_to(
    root: Path, note: Path, files: Collection[Path], *, skip: Collection[str] = SKIPPED_ROOTS
) -> list[tuple[Neighbour, Path]]:
    """Every link that could mean `note`, from marginalia then notes' text, with its source; chats quote, so skip them."""
    found = []
    for source in annotated_notes(root):
        marginalia = read_marginalia(root, source)
        for written in marginalia.wikilinks:
            if lands_on(written, note, root):
                found.append((Neighbour("in", str(Target(source)), marginalia.line(written)), source))
    for source in sorted(files):
        if source.suffix != ".md" or source.parts[0] in tuple(skip) or source == note:
            continue
        for written in extract_links((root / source).read_text(errors="replace"), source=source):
            if lands_on(written, note, root):
                found.append((Neighbour("in", str(Target(source)), f"line {written.line}"), source))
    return found


def check_marginalia(repo: Commonplace, check: bool) -> tuple[list[str], list[str]]:
    """Re-attach marginalia whose note moved, committing as the bot; report those whose note is gone, and dead links."""
    files = list(repo.paths())
    present = set(files)
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

    warnings = []
    if gone:
        warnings.append(f"Marginalia for {len(gone)} notes outlive them, kept as the record:\n" + "\n".join(gone))
    for note in annotated_notes(repo.root):
        for target in read_marginalia(repo.root, note).links:
            try:
                resolve_target(target, repo.root, files)
            except UnresolvedNote as e:
                warnings.append(f"{marginalia_path(note)}: [[{target}]] no longer resolves ({e})")
    return actions, warnings


def _resolves(target: str, root: Path, files: list[Path]) -> bool:
    try:
        resolve_target(target, root, files)
    except UnresolvedNote:
        return False
    return True


def annotated_notes(root: Path) -> list[Path]:
    """The path of every note that has marginalia, in order, whether or not the note is still there."""
    shadow = root / MARGINALIA
    return sorted(path.relative_to(shadow) for path in shadow.rglob("*.md"))
