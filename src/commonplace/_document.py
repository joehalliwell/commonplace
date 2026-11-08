"""A note read as one document: its own text, then its marginalia, what's been said about it since.

Links are found in the document, so a path in marginalia is measured from the note, and a link's line is its line in
the document: the note's lines, then its marginalia's. Each part is parsed alone, so neither's markup spills into
the other. A chat's own text quotes links rather than making them, so nothing links in from it.
"""

from collections.abc import Collection
from dataclasses import dataclass, replace
from functools import cached_property
from pathlib import Path

from commonplace._links import (
    SKIPPED_ROOTS,
    Link,
    LinkKind,
    Target,
    UnresolvedNote,
    extract_links,
    lands,
    resolve_target,
)
from commonplace._marginalia import (
    Marginalia,
    annotated_notes,
    marginalia_path,
    notes_named,
    read_marginalia,
    tagged,
    write_marginalia,
)
from commonplace._repo import Commonplace


@dataclass(frozen=True)
class Document:
    """A note's text and its marginalia, read as one, each part only when asked for."""

    root: Path
    note: Path  # Relative to the root

    @cached_property
    def text(self) -> str:
        """The note's own text, empty once the note is gone."""
        path = self.root / self.note
        return path.read_text(errors="replace") if path.exists() else ""

    @cached_property
    def marginalia(self) -> Marginalia:
        """What's been said about the note."""
        return read_marginalia(self.root, self.note)

    @cached_property
    def lines(self) -> list[str]:
        """The note's lines, then its marginalia's."""
        return self.text.split("\n") + self.marginalia.body.split("\n")

    @cached_property
    def own_links(self) -> list[Link]:
        """The links in the note's own text."""
        return extract_links(self.text, source=self.note)

    @cached_property
    def said_links(self) -> list[Link]:
        """The links in the marginalia, at their lines in the document."""
        said = extract_links(self.marginalia.body, source=self.note)
        return [replace(link, line=link.line + self._said_from) for link in said]

    @property
    def commentary(self) -> list[str]:
        """The marginalia's lines that link nowhere: what's been said about the note, rather than what it links to."""
        linked = {link.line for link in self.said_links}
        lines = enumerate(self.marginalia.body.split("\n"), self._said_from + 1)
        return [line for n, line in lines if line.strip() and n not in linked]

    def unlinked(self, target: str) -> tuple[Marginalia, int]:
        """The marginalia without the lines that link to exactly `target`, and how many went."""
        dropped = {link.line for link in self.said_links if link.target == target}
        lines = enumerate(self.marginalia.body.split("\n"), self._said_from + 1)
        return replace(self.marginalia, body="\n".join(line for n, line in lines if n not in dropped)), len(dropped)

    @cached_property
    def _said_from(self) -> int:
        """The document line the marginalia follow."""
        return self.text.count("\n") + 1


@dataclass(frozen=True)
class Neighbour:
    """A link to or from a note: the note at the other end, rooted, and where the link is written."""

    direction: str  # "out" from the note, or "in" to it
    other: str
    context: str  # The document line it's written on


def links(repo: Commonplace, spec: str, include_hidden: bool = False) -> list[Neighbour]:
    """A note's links, out then in; hidden notes at the other end left out."""
    [note] = notes_named(repo, spec)
    files = list(repo.paths())
    hidden = set() if include_hidden else tagged(repo.root, "hidden")
    found = links_from(repo.root, note, files) + links_to(repo.root, note, files)
    return [neighbour for neighbour, other in found if other not in hidden]


def links_from(root: Path, note: Path, files: Collection[Path]) -> list[tuple[Neighbour, Path | None]]:
    """Every link from `note`, with the note it lands on; one that lands nowhere is shown as written."""
    notes, present = [path for path in files if path.suffix == ".md"], set(files)
    document = Document(root, note)
    found: list[tuple[Neighbour, Path | None]] = []
    for written in document.own_links + document.said_links:
        other = lands(written, root, notes, present)
        shown = str(Target(other, written.target.partition("#")[2])) if other else written.target
        found.append((Neighbour("out", shown, document.lines[written.line - 1]), other))
    return found


def links_to(root: Path, note: Path, files: Collection[Path]) -> list[tuple[Neighbour, Path | None]]:
    """Every link that could mean `note`, with the note it's from."""
    sources = sorted({*annotated_notes(root), *(path for path in files if path.suffix == ".md")} - {note}, key=str)
    found: list[tuple[Neighbour, Path | None]] = []
    for source in sources:
        document = Document(root, source)
        own = [] if source.parts[0] in SKIPPED_ROOTS else document.own_links
        for written in own + document.said_links:
            if lands(written, root, [note], {note}) == note:
                found.append((Neighbour("in", str(Target(source)), document.lines[written.line - 1]), source))
    return found


def unlink(repo: Commonplace, from_spec: str, to_spec: str) -> int:
    """Remove a note's links to exactly `to_spec`'s target, committing as the user; returns how many went."""
    files = list(repo.paths())
    document = Document(repo.root, resolve_target(from_spec, repo.root, files).note)
    try:
        target = str(resolve_target(to_spec, repo.root, files))
    except UnresolvedNote as e:
        # A link whose note is gone can't be named any more, so take it as the marginalia write it.
        target = to_spec.removeprefix("[[").removesuffix("]]")
        if target not in (said := [found.target for found in document.said_links]):
            dead = [found for found in said if not _resolves(found, repo.root, files)]
            hint = f"; a link whose note is gone is removed as written: {', '.join(dead)}" if dead else ""
            raise UnresolvedNote(f"{e}{hint}") from e
    marginalia, removed = document.unlinked(target)
    if not removed:
        raise ValueError(f"'{from_spec}' has no link to {target}")
    write_marginalia(repo, marginalia)
    repo.commit(f"Unlink {from_spec} from {target}", auto_index=False, as_user=True)
    return removed


def dead_links(repo: Commonplace) -> list[str]:
    """A warning for each wikilink in marginalia whose note, or span in it, can no longer be found."""
    files = list(repo.paths())
    warnings = []
    for note in annotated_notes(repo.root):
        for written in Document(repo.root, note).said_links:
            try:
                if written.kind is LinkKind.WIKILINK:
                    resolve_target(written.target, repo.root, files)
            except UnresolvedNote as e:
                warnings.append(f"{marginalia_path(note)}: [[{written.target}]] no longer resolves ({e})")
    return warnings


def _resolves(target: str, root: Path, files: list[Path]) -> bool:
    try:
        resolve_target(target, root, files)
    except UnresolvedNote:
        return False
    return True
