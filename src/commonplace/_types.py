"""The nodes of the repository's graph, each type the locus of policy for its kind, and the paths that identify them.

A node type is commonplace's: a `Note`, a `Blob` or a `Source`. It is not OKF's `type`, the frontmatter key that
names a kind of note (a chat, a topic), so never a `Node` subclass.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from commonplace._config import MARGINALIA
from commonplace._links import Edge, Target, extract_links
from commonplace._utils import override

if TYPE_CHECKING:
    from commonplace._config import Config
    from commonplace._fetch._types import Fetcher

#: A note's metadata, serialised as its frontmatter, which is where OKF's keys live.
type Metadata = dict[str, Any]
type Pathlike = str | Path


@dataclass(frozen=True)
class RepoPath:
    """
    Immutable reference to a note: its path, which corresponds to an OKF concept ID, at a version.

    Invariants:
    - path is normalised and relative to the repository root, as note links resolve
    - ref is git's id for the note's committed content, or None for a note not yet committed
    - instances are hashable and suitable as dict keys
    """

    path: Path  # Relative to repo root
    ref: str | None = None

    def __post_init__(self):
        path = Path(os.path.normpath(self.path))
        if path.is_absolute() or path.parts[:1] == ("..",):
            raise ValueError(f"RepoPath must stay inside the repository: {self.path}")
        object.__setattr__(self, "path", path)

    def __str__(self) -> str:
        return f"{self.path}@{self.ref[:8]}" if self.ref else str(self.path)


class Node:
    """A node in the repository's graph; what is particular to a kind of node lives on its subtype."""


@dataclass(frozen=True)
class Source(Node):
    """Where captures come from: a node with no file, owning its importers, its fetcher, and the tree its notes land in."""

    name: str
    tree: Path
    importer_types: tuple[type, ...]  # Each built with this source, which is how it knows its name and tree
    fetcher_type: "type[Fetcher] | None"
    #: Whether its notes' own text quotes links rather than making them.
    quotes: ClassVar[bool] = False
    #: The frontmatter keys in which a note records where it came from.
    PROVENANCE: ClassVar[tuple[str, str]] = ("source", "source_export")

    @cached_property
    def importers(self) -> tuple[Any, ...]:
        """Its importers, in the order a capture is offered to them."""
        return tuple(importer(self) for importer in self.importer_types)

    def provenance(self, archive: str) -> dict[str, str]:
        """What a note it lands records of where it came from: this source, and the archive it was read from."""
        return dict(zip(self.PROVENANCE, (self.name, archive), strict=True))

    def fetcher(self, config: "Config") -> "Fetcher":
        """Its fetcher, built per run so that the configured User-Agent, a repo's own included, reaches it."""
        assert self.fetcher_type is not None, f"{self.name} has no fetcher"
        return self.fetcher_type.configured(self, config)


@dataclass(frozen=True)
class ChatSource(Source):
    """A source of closed conversations, accumulated under `chats/`; a chat's text quotes links rather than making them."""

    tree: Path = field(init=False)
    quotes: ClassVar[bool] = True
    #: Where every chat source's tree is.
    ROOT: ClassVar[Path] = Path("chats")

    def __post_init__(self) -> None:
        object.__setattr__(self, "tree", self.ROOT / self.name)


@dataclass(frozen=True)
class MirrorSource(Source):
    """A source of live upstream state, mirrored into a tree it owns: rewritten to match, and pruned."""


@dataclass(frozen=True)
class Blob(Node):
    """An archive as captured, under `.commonplace/blobs/`: immutable, and what a rendered note names as its provenance."""

    path: Path  # Relative to the root


@dataclass(frozen=True)
class Marginalia:
    """What's been said about a note since: labels on its node, and a second body, a log of what's been said."""

    note: Path  # The annotated note, relative to the root
    tags: list[str] = field(default_factory=list)
    body: str = ""
    offset: int = field(default=0, compare=False)  # The lines of their file before the body, as read

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


@dataclass
class Note(Node):
    """A markdown file in the commonplace, of the kind its `type` names; it corresponds to an OKF concept document.

    It is a node in the repository's graph, its path its id. Read back from the repository it carries its source and
    its marginalia, which add labels to its own tags, edges to its own links, and a second body.
    """

    repo_path: RepoPath
    body: str
    metadata: Metadata = field(default_factory=dict)
    marginalia: Marginalia = field(default=None, compare=False)  # type: ignore[assignment]  # Empty unless read back
    text: str = field(default="", compare=False)  # The file as read back, which its own edges' lines count in
    source: Source | None = field(default=None, compare=False)  # As read back: the one it names, or whose tree holds it

    @classmethod
    def compose(cls, repo_path: RepoPath, type: str, title: str, body: str, metadata: Metadata | None = None) -> "Note":
        """A note whose `type` and `title` lead and override `metadata`."""
        return cls(repo_path, body, override(metadata or {}, repo_path, type=type, title=title))

    def __post_init__(self) -> None:
        if self.marginalia is None:
            self.marginalia = Marginalia(self.repo_path.path)

    @cached_property
    def labels(self) -> list[str]:
        """Its own tags, then those its marginalia add."""
        return list(dict.fromkeys([*(self.metadata.get("tags") or []), *self.marginalia.tags]))

    @property
    def hidden(self) -> bool:
        """Whether it's labelled `hidden`: kept, but left out of search, listings and links unless asked for."""
        return "hidden" in self.labels

    @property
    def edges(self) -> list[Edge]:
        """Every link it makes: its own body's, then its marginalia's."""
        return self._own + self.said

    @cached_property
    def said(self) -> list[Edge]:
        """The edges its marginalia add, at their lines in the marginalia's file."""
        path, offset = self.repo_path.path, self.marginalia.offset
        said = extract_links(self.marginalia.body, source=MARGINALIA / path, metadata={})
        return [Edge(path, replace(link, line=link.line + offset)) for link in said]

    def line(self, edge: Edge) -> str:
        """The line `edge` is written on."""
        if edge.link.source == self.repo_path.path:
            return self.text.split("\n")[edge.link.line - 1]
        return self.marginalia.body.split("\n")[edge.link.line - self.marginalia.offset - 1]

    @property
    def commentary(self) -> list[str]:
        """The marginalia's lines that link nowhere: what's been said about the note, rather than what it links to."""
        linked = {edge.link.line for edge in self.said}
        return [line for n, line in self._said_lines() if line.strip() and n not in linked]

    def unlinked(self, target: str) -> tuple[Marginalia, int]:
        """Its marginalia without the lines that link to exactly `target`, and how many went."""
        dropped = {edge.link.line for edge in self.said if edge.link.target == target}
        kept = "\n".join(line for n, line in self._said_lines() if n not in dropped)
        return replace(self.marginalia, body=kept), len(dropped)

    @cached_property
    def _own(self) -> list[Edge]:
        path = self.repo_path.path
        # Text that only quotes links makes none, but what the frontmatter cites, its provenance, is still the note's.
        quotes = self.source is not None and self.source.quotes
        found = extract_links(self.text, source=path, body=not quotes, metadata=self.metadata)
        return [Edge(path, link) for link in found]

    def _said_lines(self) -> Iterator[tuple[int, str]]:
        return enumerate(self.marginalia.body.split("\n"), self.marginalia.offset + 1)
