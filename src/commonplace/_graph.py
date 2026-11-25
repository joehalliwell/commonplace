"""The repository's graph, kept in the index: each file version's labels, and its edges, landed on the node they name.

A node is its note and its marginalia, two files, and each version of either, committed or not, is found by its path
and git's id for its content, so a file is read once per version and nothing is served stale. Where an edge lands
depends on every other file, so edges land against a fingerprint of the repository's files: a version read since is
landed by the next pass that has the files, and every edge again whenever they change. A change to what is read from a
file reaches files read before it only through `index --rebuild-graph`.
"""

import hashlib
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Self

from commonplace._cache import connect
from commonplace._links import Edge, Files, Link, LinkKind

if TYPE_CHECKING:
    from commonplace._types import Marginalia, Note

#: A file version: its path, relative to the root, and git's id for its content.
type Key = tuple[str, str]

_FILES = "SELECT id, path, content_id FROM graph_files"
_EDGE = "e.from_node, e.to_node, f.path, e.line, e.target, e.kind, e.text"
_JOINED = "graph_edges e JOIN graph_files f ON f.id = e.file_id"
#: An edge that may be broken: it landed on no one node, or it names a span in the one it landed on.
_DOUBTFUL = "e.to_node IS NULL OR instr(e.target, '#') > 0"


class Half(NamedTuple):
    """What one file contributes to its node: labels, and the edges written in it."""

    labels: list[str]
    edges: list[Edge]


class FileSet(NamedTuple):
    """The files edges land on: a fingerprint of them, and their index, built only if some edge must land."""

    stamp: str
    files: Callable[[], Files]


def own(note: "Note") -> Half:
    """What a note's own file contributes: its frontmatter's tags, and the edges its text makes."""
    return Half([str(tag) for tag in note.metadata.get("tags") or []], note.own)


def said(marginalia: "Marginalia") -> Half:
    """What a note's marginalia contribute: their tags, and the edges they make."""
    return Half([str(tag) for tag in marginalia.tags], marginalia.edges)


def fingerprint(files: Iterable[Path]) -> str:
    """What edges land against: every file there is, by path."""
    return hashlib.sha256("\0".join(sorted(path.as_posix() for path in files)).encode()).hexdigest()


def _edge(row: tuple) -> Edge:
    from_node, to_node, source, line, target, kind, text = row
    to = Path(to_node) if to_node is not None else target
    return Edge(Path(from_node), Link(Path(source), line, target, LinkKind(kind), text), to)


def _in_order(rows: Iterable[tuple]) -> list[Edge]:
    """Edges by the node they're from, each node's own text's before its marginalia's, then by line, then as stored."""
    edges = [_edge(row) for row in rows]
    return sorted(edges, key=lambda edge: (edge.node, edge.link.source != edge.node, edge.link.line))


class GraphStore:
    """One repository's graph, in its cache database, which refuses one newer than this release."""

    def __init__(self, db: Path):
        self._conn = connect(db)

    def sync(self, current: Iterable[Key], read: Callable[[Key], Half], prune: bool, files: FileSet | None) -> None:
        """`read` each version in `current` the store lacks, drop the rest if `prune`, and land what is unlanded
        against `files`, every edge if they have changed; without `files`, new edges wait for a pass that has them.
        With nothing to do, it writes nothing, so it waits on no writer."""
        stored = {(path, content_id): id_ for id_, path, content_id in self._conn.execute(_FILES)}
        current = set(current)
        stale = [(id_,) for key, id_ in stored.items() if key not in current] if prune else []
        new = [key for key in current if key not in stored]
        if not (stale or new or (files is not None and self._unlanded(files))):
            return
        with self._conn:
            self._conn.executemany("DELETE FROM graph_files WHERE id = ?", stale)
            for key in new:
                self._insert(key, read(key))
            if files is not None:
                self._land(files)

    def _unlanded(self, files: FileSet) -> bool:
        """Whether some edge must land: the files have changed, or a version has been read but not landed."""
        changed = self._conn.execute("SELECT value FROM graph_state WHERE key = 'files'").fetchone() != (files.stamp,)
        return (
            changed or self._conn.execute("SELECT 1 FROM graph_files WHERE landed = 0 LIMIT 1").fetchone() is not None
        )

    def _insert(self, key: Key, half: Half) -> None:
        """Store one file version and what it contributes, its edges not yet landed."""
        # Ignored if another process stored it since this one looked: each found it missing, and either may store it.
        stored = self._conn.execute("INSERT OR IGNORE INTO graph_files (path, content_id) VALUES (?, ?)", key)
        if not stored.rowcount:
            return
        id_ = stored.lastrowid
        self._conn.executemany("INSERT INTO graph_labels VALUES (?, ?)", [(id_, label) for label in half.labels])
        rows = [
            (id_, e.node.as_posix(), e.link.line, e.link.target, e.link.kind.value, e.link.text) for e in half.edges
        ]
        self._conn.executemany(
            "INSERT INTO graph_edges (file_id, from_node, line, target, kind, text) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )

    def _land(self, files: FileSet) -> None:
        """Land the edges of every version not yet landed, or of every version if the files have changed."""
        changed = self._conn.execute("SELECT value FROM graph_state WHERE key = 'files'").fetchone() != (files.stamp,)
        unlanded = "" if changed else "WHERE f.landed = 0"
        rows = self._conn.execute(f"SELECT e.id, {_EDGE} FROM {_JOINED} {unlanded}").fetchall()
        if rows:
            index = files.files()
            landed = [(_landed_on(index.landing(_edge(row[1:]))), row[0]) for row in rows]
            self._conn.executemany("UPDATE graph_edges SET to_node = ? WHERE id = ?", landed)
        self._conn.execute(f"UPDATE graph_files SET landed = 1 {'' if changed else 'WHERE landed = 0'}")
        self._conn.execute("INSERT OR REPLACE INTO graph_state VALUES ('files', ?)", (files.stamp,))

    def in_edges(self, node: Path) -> list[Edge]:
        """Every edge from another node that lands on `node`."""
        query = f"SELECT {_EDGE} FROM {_JOINED} WHERE e.to_node = ? AND e.from_node != ? ORDER BY e.id"
        return _in_order(self._conn.execute(query, (node.as_posix(),) * 2))

    def doubtful(self) -> list[Edge]:
        """Every edge that may be broken: those that landed on no one node, and those naming a span."""
        return _in_order(self._conn.execute(f"SELECT {_EDGE} FROM {_JOINED} WHERE {_DOUBTFUL} ORDER BY e.id"))

    def out_edges(self, node: Path) -> list[Edge]:
        """Every edge `node` makes, in its own text then its marginalia."""
        query = f"SELECT {_EDGE} FROM {_JOINED} WHERE e.from_node = ? ORDER BY e.id"
        return _in_order(self._conn.execute(query, (node.as_posix(),)))

    def labels(self, node: Path, marginalia: Path) -> list[str]:
        """`node`'s labels: its own file's, then those its marginalia, at `marginalia`, add, each once."""
        own, said = node.as_posix(), marginalia.as_posix()
        query = "SELECT label FROM graph_labels l JOIN graph_files f ON f.id = l.file_id WHERE f.path IN (?, ?)"
        rows = self._conn.execute(f"{query} ORDER BY f.path = ?, l.rowid", (own, said, said))
        return list(dict.fromkeys(label for (label,) in rows))

    def clear(self) -> None:
        """Forget every file version, so each is read again."""
        with self._conn:
            self._conn.execute("DELETE FROM graph_files")
            self._conn.execute("DELETE FROM graph_state")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _landed_on(edge: Edge) -> str | None:
    """Where a landed edge lands, if on one node."""
    return edge.to.as_posix() if isinstance(edge.to, Path) else None
