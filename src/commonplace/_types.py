"""Notes, the nodes of the repository's graph, and the paths that identify them."""

import os
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any

from commonplace._config import MARGINALIA
from commonplace._links import Edge, Target, extract_links
from commonplace._utils import override

#: A note's metadata, serialised as its frontmatter, which is where OKF's keys live.
type Metadata = dict[str, Any]
type Pathlike = str | Path

# Directories whose notes' own bodies quote links rather than making them.
QUOTING_ROOTS: tuple[str, ...] = ("chats",)


@dataclass(frozen=True)
class RepoPath:
    """
    Immutable reference to a note: its path, which corresponds to an OKF concept ID, at a version.

    Invariants:
    - path is normalised and relative to the repository root, as note links resolve
    - ref is a git SHA (not branch name), or None for a note not yet committed
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


@dataclass(frozen=True)
class Marginalia:
    """What's been said about a note since: labels on its node, and a second body, a log of what's been said."""

    note: Path  # The annotated note, relative to the root
    ref: str | None = None  # The commit that last changed the note when it was last annotated
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
class Note:
    """A markdown file in the commonplace, of the kind its `type` names; it corresponds to an OKF concept document.

    It is a node in the repository's graph, its path its id. Read back from the repository it carries its
    marginalia, which add labels to its own tags, edges to its own links, and a second body.
    """

    repo_path: RepoPath
    body: str
    metadata: Metadata = field(default_factory=dict)
    marginalia: Marginalia | None = field(default=None, compare=False)  # As read back
    text: str = field(default="", compare=False)  # The file as read back, which its own edges' lines count in

    @classmethod
    def compose(cls, repo_path: RepoPath, type: str, title: str, body: str, metadata: Metadata | None = None) -> "Note":
        """A note whose `type` and `title` lead and override `metadata`."""
        return cls(repo_path, body, override(metadata or {}, repo_path, type=type, title=title))

    @cached_property
    def labels(self) -> list[str]:
        """Its own tags, then those its marginalia add."""
        return list(dict.fromkeys([*(self.metadata.get("tags") or []), *self._marginalia.tags]))

    @property
    def edges(self) -> list[Edge]:
        """Every link it makes: its own body's, unless that only quotes them, then its marginalia's."""
        return self._own + self.said

    @cached_property
    def said(self) -> list[Edge]:
        """The edges its marginalia add, at their lines in the marginalia's file."""
        path, offset = self.repo_path.path, self._marginalia.offset
        said = extract_links(self._marginalia.body, source=MARGINALIA / path)
        return [Edge(path, replace(link, line=link.line + offset)) for link in said]

    def line(self, edge: Edge) -> str:
        """The line `edge` is written on."""
        if edge.link.source == self.repo_path.path:
            return self.text.split("\n")[edge.link.line - 1]
        return self._marginalia.body.split("\n")[edge.link.line - self._marginalia.offset - 1]

    @property
    def commentary(self) -> list[str]:
        """The marginalia's lines that link nowhere: what's been said about the note, rather than what it links to."""
        linked = {edge.link.line for edge in self.said}
        return [line for n, line in self._said_lines() if line.strip() and n not in linked]

    def unlinked(self, target: str) -> tuple[Marginalia, int]:
        """Its marginalia without the lines that link to exactly `target`, and how many went."""
        dropped = {edge.link.line for edge in self.said if edge.link.target == target}
        kept = "\n".join(line for n, line in self._said_lines() if n not in dropped)
        return replace(self._marginalia, body=kept), len(dropped)

    @cached_property
    def _own(self) -> list[Edge]:
        path = self.repo_path.path
        quotes = path.parts[0] in QUOTING_ROOTS
        return [] if quotes else [Edge(path, link) for link in extract_links(self.text, source=path)]

    @property
    def _marginalia(self) -> Marginalia:
        return self.marginalia or Marginalia(self.repo_path.path)

    def _said_lines(self) -> Iterator[tuple[int, str]]:
        return enumerate(self._marginalia.body.split("\n"), self._marginalia.offset + 1)
