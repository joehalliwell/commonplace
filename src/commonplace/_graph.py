"""The repository as a graph: every shared file is a node, its path its id, and every link a note makes is an edge.

A note's marginalia are part of its node, kept under `.commonplace/marginalia/` because another writer may own the
note: they add labels to the note's own tags, edges to its own links, and a second body. An edge is written at a
line of one body's file and lands from the note, so a path in marginalia is measured from the note. A chat's own
body quotes links rather than making them. Git versions the whole graph: a `Graph` is one snapshot of it, a node
keeps its id across a rename (`check_marginalia`), and a node's labels and edges derive from its bodies alone, so
they can be cached by blob in the index, which is a cache.
"""

import fnmatch
import os
from collections.abc import Callable, Collection, Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import date
from functools import cached_property
from pathlib import Path
from urllib.parse import unquote

from commonplace._links import Link, LinkKind, Target, extract_links
from commonplace._marginalia import (
    Marginalia,
    annotated_notes,
    marginalia_path,
    parse_marginalia,
    read_marginalia,
    write_marginalia,
)
from commonplace._repo import Commonplace
from commonplace._utils import load_frontmatter

# Directories whose notes' own bodies quote links rather than making them.
QUOTING_ROOTS: tuple[str, ...] = ("chats",)


class UnresolvedNote(ValueError):
    """A spec that names no note, or more than one where one was meant."""


@dataclass(frozen=True)
class Edge:
    """A link from a node, as written in one of its bodies."""

    node: Path  # The node it's from: a path in it is measured from here
    link: Link  # Its source is the file of the body it's written in, its line the line there


@dataclass(frozen=True)
class BrokenLink:
    """An edge that lands nowhere, and where it probably meant to."""

    link: Link
    reason: str
    suggestion: Path | None = None


@dataclass(frozen=True)
class Node:
    """A node, read from its bodies only when asked: the note's own, and its marginalia."""

    root: Path
    id: Path  # Relative to the root

    @cached_property
    def body(self) -> str:
        """The note's own text, frontmatter and all; empty for a file that isn't a note, or a note that's gone."""
        path = self.root / self.id
        return path.read_text(errors="replace") if self.id.suffix == ".md" and path.exists() else ""

    @cached_property
    def marginalia(self) -> Marginalia:
        """The node's second body, and the labels it adds."""
        return parse_marginalia(self.id, self._sidecar)

    @cached_property
    def labels(self) -> list[str]:
        """The note's own tags, then those its marginalia add."""
        own = load_frontmatter(self.body)[0].get("tags") or []
        return list(dict.fromkeys([*own, *self.marginalia.tags]))

    @property
    def edges(self) -> list[Edge]:
        """Every link the node makes: its own body's, unless that only quotes them, then its marginalia's."""
        return self._own + self.said

    @cached_property
    def said(self) -> list[Edge]:
        """The edges its marginalia add."""
        said = extract_links(self.marginalia.body, source=marginalia_path(self.id))
        return [Edge(self.id, replace(link, line=link.line + self._said_from)) for link in said]

    def line(self, edge: Edge) -> str:
        """The line `edge` is written on."""
        return (self.body if edge.link.source == self.id else self._sidecar).split("\n")[edge.link.line - 1]

    @property
    def commentary(self) -> list[str]:
        """The marginalia's lines that link nowhere: what's been said about the note, rather than what it links to."""
        linked = {edge.link.line for edge in self.said}
        return [line for n, line in self._said_lines() if line.strip() and n not in linked]

    def unlinked(self, target: str) -> tuple[Marginalia, int]:
        """The marginalia without the lines that link to exactly `target`, and how many went."""
        dropped = {edge.link.line for edge in self.said if edge.link.target == target}
        kept = "\n".join(line for n, line in self._said_lines() if n not in dropped)
        return replace(self.marginalia, body=kept), len(dropped)

    @cached_property
    def _own(self) -> list[Edge]:
        quotes = self.id.parts[0] in QUOTING_ROOTS
        return [] if quotes else [Edge(self.id, link) for link in extract_links(self.body, source=self.id)]

    @cached_property
    def _sidecar(self) -> str:
        path = self.root / marginalia_path(self.id)
        return path.read_text() if path.exists() else ""

    @cached_property
    def _said_from(self) -> int:
        """The lines of the marginalia's file before their body."""
        return self._sidecar.count("\n") - self.marginalia.body.count("\n")

    def _said_lines(self) -> Iterator[tuple[int, str]]:
        return enumerate(self.marginalia.body.split("\n"), self._said_from + 1)


class Graph:
    """A snapshot of the repository's graph: a node for each shared file, and for each gone note still annotated."""

    def __init__(self, root: Path, files: Iterable[Path]) -> None:
        self.root = root
        self.files = set(files)
        self._present = self.files | {parent for path in self.files for parent in path.parents}
        self._by_name: dict[str, list[Path]] = {}
        for path in sorted(self.files):
            for key in {path.name, path.stem}:
                self._by_name.setdefault(key, []).append(path)
        self._nodes: dict[Path, Node] = {}

    def node(self, id: Path) -> Node:
        """The node `id` names."""
        if id not in self._nodes:
            self._nodes[id] = Node(self.root, id)
        return self._nodes[id]

    @cached_property
    def notes(self) -> list[Node]:
        """Every node that makes edges: each note, and each one gone whose marginalia remain."""
        ids = {path for path in self.files if path.suffix == ".md"} | set(annotated_notes(self.root))
        return [self.node(id) for id in sorted(ids, key=str)]

    def named(self, name: str) -> list[Path]:
        """The nodes `name` writes as a wikilink would, in order."""
        return [path for path in self._by_name.get(Path(name).name, []) if is_named(path, name)]

    def lands(self, edge: Edge) -> list[Path]:
        """Every node `edge` could mean: each one a wikilink names, or the file or directory a path is at."""
        if edge.link.kind is LinkKind.WIKILINK:
            return self.named(edge.link.target.split("#")[0])
        landing = _landing(edge, self.root)
        if landing is None or not landing.is_relative_to(self.root):
            return []
        return [path] if (path := landing.relative_to(self.root)) in self._present else []

    def into(self, id: Path) -> list[Edge]:
        """Every edge from another node that could mean `id`."""
        return [edge for node in self.notes if node.id != id for edge in node.edges if id in self.lands(edge)]

    def check(self) -> list[BrokenLink]:
        """Every edge that lands on no node, or on no span it names."""
        return [broken for node in self.notes for edge in node.edges if (broken := self._broken(edge))]

    def resolve(self, spec: str) -> list[Path]:
        """The notes a spec names: exactly one, or every match of a glob, else `UnresolvedNote`; an edge may mean several."""
        name = spec.removeprefix("[[").removesuffix("]]").split("#")[0].strip()
        if "*" in name:
            notes = sorted(path for path in self.files if path.suffix == ".md")
            if not (matched := [path for path in notes if fnmatch.fnmatchcase(path.as_posix(), name.lstrip("/"))]):
                raise UnresolvedNote(f"'{spec}' matches no note")
            return matched
        found = [path for path in self.named(name) if path.suffix == ".md"]
        if not found:
            raise UnresolvedNote(f"'{spec}' names no note")
        if len(found) > 1:
            candidates = "\n".join(f"  /{path.with_suffix('').as_posix()}" for path in found)
            raise UnresolvedNote(f"'{spec}' names {len(found)} notes; say which:\n{candidates}")
        return found

    def resolve_target(self, spec: str) -> Target:
        """The one note `spec` names, with its span checked against the note: `#Heading` or `#"exact phrase"`."""
        if "*" in spec:
            raise UnresolvedNote(f"'{spec}' is a glob; a link joins one note to one note")
        [note] = self.resolve(spec)
        _, _, fragment = spec.removeprefix("[[").removesuffix("]]").partition("#")
        if fragment and not _has_span(self.root / note, fragment):
            raise UnresolvedNote(f"'{spec}': no such heading or phrase in /{note.with_suffix('').as_posix()}")
        return Target(note, fragment)

    def _broken(self, edge: Edge) -> BrokenLink | None:
        page, _, span = edge.link.target.partition("#")
        if landed := self.lands(edge):
            wikilink = edge.link.kind is LinkKind.WIKILINK
            if not wikilink or not span or any(_has_span(self.root / path, span) for path in landed):
                return None
            return BrokenLink(edge.link, "no such heading or phrase")
        named = self._by_name.get(Path(unquote(page)).name, [])
        return BrokenLink(edge.link, self._why_broken(edge), named[0] if len(named) == 1 else None)

    def _why_broken(self, edge: Edge) -> str:
        if edge.link.kind is LinkKind.WIKILINK:
            return "no note with that name"
        if (landing := _landing(edge, self.root)) is None:
            return "empty target"
        if not landing.is_relative_to(self.root):
            return "outside the repository"
        return "on disk but not in the repository" if landing.exists() else "no such file"


def is_named(path: Path, name: str) -> bool:
    """True if `name` is how a wikilink would write `path`: its tail, or from `/` its whole path, either extension."""
    return any(
        f"/{written}" == name or written == name or written.endswith(f"/{name}")
        for written in (path.as_posix(), path.with_suffix("").as_posix())
    )


def _landing(edge: Edge, root: Path) -> Path | None:
    """Where a path link or citation points, if anywhere; a citation is written from the root, a path from the note."""
    if not (target := unquote(edge.link.target.split("#")[0].split("?")[0])):
        return None
    root_relative = edge.link.kind is LinkKind.CITATION or target.startswith("/")
    base = root if root_relative else root / edge.node.parent
    return Path(os.path.normpath(base / target.lstrip("/")))


def _has_span(path: Path, fragment: str) -> bool:
    """Whether the note has a heading reading `fragment` exactly, or for `"phrase"`, contains the phrase."""
    text = path.read_text(errors="replace")
    if len(fragment) > 1 and fragment.startswith('"') and fragment.endswith('"'):
        return fragment[1:-1] in text
    return any(line.lstrip("#").strip() == fragment for line in text.splitlines() if line.startswith("#"))


def summarize(broken: Collection[BrokenLink]) -> list[str]:
    """One report per file of what no longer resolves."""
    by_source: dict[Path, list[BrokenLink]] = {}
    for item in broken:
        by_source.setdefault(item.link.source, []).append(item)

    summaries = []
    for source, items in sorted(by_source.items()):
        count = f"{len(items)} links that go" if len(items) > 1 else "1 link that goes"
        lines = [f"{source}: {count} nowhere"]
        for item in sorted(items, key=lambda i: i.link.line):
            suggestion = f" — same name at {item.suggestion}" if item.suggestion else ""
            lines.append(f"  line {item.link.line}: {item.link.target} ({item.reason}){suggestion}")
        summaries.append("\n".join(lines))
    return summaries


# --- Edits and queries ------------------------------------------------------


def notes_named(graph: Graph, spec: str) -> list[Path]:
    """The whole notes `spec` names; a span is refused, since marginalia speak for a whole note."""
    if "#" in spec:
        raise UnresolvedNote(f"'{spec}' names a span; marginalia belong to whole notes")
    return graph.resolve(spec)


def tag(repo: Commonplace, spec: str, tags: list[str]) -> list[Path]:
    """Label the notes `spec` names, in their marginalia, committing as the user; returns the notes."""
    return _retag(repo, spec, lambda marginalia: marginalia.tagged(*tags), f"Tag {spec}: {', '.join(tags)}")


def untag(repo: Commonplace, spec: str, tags: list[str]) -> list[Path]:
    """Remove labels from the notes `spec` names' marginalia, committing as the user; returns the notes."""
    return _retag(repo, spec, lambda marginalia: marginalia.untagged(*tags), f"Untag {spec}: {', '.join(tags)}")


def _retag(repo: Commonplace, spec: str, change: Callable[[Marginalia], Marginalia], message: str) -> list[Path]:
    notes = notes_named(repo.graph(), spec)
    for note in notes:
        marginalia = change(read_marginalia(repo.root, note))
        write_marginalia(repo, replace(marginalia, ref=repo.make_repo_path(note).ref))
    repo.commit(message, auto_index=False, as_user=True)
    return notes


def link(repo: Commonplace, from_spec: str, to_spec: str, why: str, on: date | None = None) -> Target:
    """Add an edge from a whole note to a note or a span in one, in its marginalia, committing as the user."""
    if "#" in from_spec:
        raise UnresolvedNote(f"'{from_spec}' names a span; marginalia belong to whole notes")
    graph = repo.graph()
    source, target = graph.resolve_target(from_spec).note, graph.resolve_target(to_spec)
    today = date.today()  # noqa: DTZ011 - the user's local day, as the journal's
    marginalia = read_marginalia(repo.root, source).linked(target, why, on or today)
    write_marginalia(repo, replace(marginalia, ref=repo.make_repo_path(source).ref))
    repo.commit(f"Link {from_spec} to {target}", auto_index=False, as_user=True)
    return target


def unlink(repo: Commonplace, from_spec: str, to_spec: str) -> int:
    """Remove a note's edges to exactly `to_spec`'s target from its marginalia, committing as the user."""
    graph = repo.graph()
    node = graph.node(graph.resolve_target(from_spec).note)
    try:
        target = str(graph.resolve_target(to_spec))
    except UnresolvedNote as e:
        # An edge whose note is gone can't be named any more, so take it as the marginalia write it.
        target = to_spec.removeprefix("[[").removesuffix("]]")
        if target not in [said.link.target for said in node.said]:
            dead = [said.link.target for said in node.said if not graph.lands(said)]
            hint = f"; a link whose note is gone is removed as written: {', '.join(dead)}" if dead else ""
            raise UnresolvedNote(f"{e}{hint}") from e
    marginalia, removed = node.unlinked(target)
    if not removed:
        raise ValueError(f"'{from_spec}' has no link to {target}")
    write_marginalia(repo, marginalia)
    repo.commit(f"Unlink {from_spec} from {target}", auto_index=False, as_user=True)
    return removed


@dataclass(frozen=True)
class Neighbour:
    """An edge to or from a note: the node at the other end, rooted, and the line it's written on."""

    direction: str  # "out" from the note, or "in" to it
    other: str
    context: str


def links(graph: Graph, note: Path, include_hidden: bool = False) -> list[Neighbour]:
    """A note's edges, out then in; those whose other end is labelled `hidden` left out unless asked for."""

    def shown(other: Path) -> bool:
        return include_hidden or "hidden" not in graph.node(other).labels

    node, found = graph.node(note), []
    for edge in node.edges:
        match graph.lands(edge):
            case [other] if not shown(other):
                continue
            case [other]:
                found.append(Neighbour("out", str(Target(other, edge.link.target.partition("#")[2])), node.line(edge)))
            case _:
                found.append(Neighbour("out", edge.link.target, node.line(edge)))
    into = graph.into(note)
    return found + [Neighbour("in", str(Target(e.node)), graph.node(e.node).line(e)) for e in into if shown(e.node)]
