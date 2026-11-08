"""A note read as one document: its own text, then its marginalia, what's been said about it since.

Links are found in documents and landed on the repository's tree, so a path in marginalia is measured from the note,
and a link's line is its line in the document: the note's lines, then its marginalia's. Each part is parsed alone,
so neither's markup spills into the other. A chat's own text quotes links rather than making them.
"""

from dataclasses import dataclass, replace
from functools import cached_property
from pathlib import Path

from commonplace._links import BrokenLink, Link, Target, Tree, UnresolvedNote, extract_links
from commonplace._marginalia import Marginalia, annotated_notes, notes_named, read_marginalia, tagged, write_marginalia
from commonplace._repo import Commonplace

# Directories whose notes' own text quotes links rather than making them.
QUOTING_ROOTS: tuple[str, ...] = ("chats",)


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

    @property
    def links(self) -> list[Link]:
        """Every link in the document, in order."""
        return self.own_links + self.said_links

    @cached_property
    def own_links(self) -> list[Link]:
        """The links in the note's own text, unless it only quotes them."""
        return [] if self.note.parts[0] in QUOTING_ROOTS else extract_links(self.text, source=self.note)

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


def documents(tree: Tree) -> list[Document]:
    """Every note's document: each note in the tree, and each one gone that still has marginalia."""
    notes = {path for path in tree.files if path.suffix == ".md"} | set(annotated_notes(tree.root))
    return [Document(tree.root, note) for note in sorted(notes, key=str)]


@dataclass(frozen=True)
class Neighbour:
    """A link to or from a note: the note at the other end, rooted, and where the link is written."""

    direction: str  # "out" from the note, or "in" to it
    other: str
    context: str  # The document line it's written on


def links(repo: Commonplace, spec: str, include_hidden: bool = False) -> list[Neighbour]:
    """A note's links, out then in; hidden notes at the other end left out."""
    [note] = notes_named(repo, spec)
    tree = repo.tree()
    hidden = set() if include_hidden else {str(Target(other)) for other in tagged(repo.root, "hidden")}
    found = links_from(tree, note) + links_to(tree, note)
    return [neighbour for neighbour in found if neighbour.other.partition("#")[0] not in hidden]


def links_from(tree: Tree, note: Path) -> list[Neighbour]:
    """Every link from `note`, to the one file it lands on, rooted; one landing on none, or several, as written."""
    document = Document(tree.root, note)
    return [
        Neighbour("out", _shown(written, tree.lands(written)), document.lines[written.line - 1])
        for written in document.links
    ]


def _shown(link: Link, landed: list[Path]) -> str:
    return str(Target(landed[0], link.target.partition("#")[2])) if len(landed) == 1 else link.target


def links_to(tree: Tree, note: Path) -> list[Neighbour]:
    """Every link that could mean `note`, from the note it's in."""
    return [
        Neighbour("in", str(Target(document.note)), document.lines[written.line - 1])
        for document in documents(tree)
        if document.note != note
        for written in document.links
        if note in tree.lands(written)
    ]


def check_links(tree: Tree) -> list[BrokenLink]:
    """Every link in every document that lands on nothing in the tree."""
    return [broken for document in documents(tree) for link in document.links if (broken := tree.broken(link))]


def unlink(repo: Commonplace, from_spec: str, to_spec: str) -> int:
    """Remove a note's links to exactly `to_spec`'s target, committing as the user; returns how many went."""
    tree = repo.tree()
    document = Document(repo.root, tree.resolve_target(from_spec).note)
    try:
        target = str(tree.resolve_target(to_spec))
    except UnresolvedNote as e:
        # A link whose note is gone can't be named any more, so take it as the marginalia write it.
        target = to_spec.removeprefix("[[").removesuffix("]]")
        if target not in [said.target for said in document.said_links]:
            dead = [said.target for said in document.said_links if not tree.lands(said)]
            hint = f"; a link whose note is gone is removed as written: {', '.join(dead)}" if dead else ""
            raise UnresolvedNote(f"{e}{hint}") from e
    marginalia, removed = document.unlinked(target)
    if not removed:
        raise ValueError(f"'{from_spec}' has no link to {target}")
    write_marginalia(repo, marginalia)
    repo.commit(f"Unlink {from_spec} from {target}", auto_index=False, as_user=True)
    return removed
