"""Marginalia: what's been said about a note since, kept in a shadow tree beside it rather than in it.

A note's sidecar sits at its path under `.commonplace/marginalia/`. Notes owned by another system of record
are rewritten on every fetch, and primitives are immutable, so this is the one place to say anything about any note.
Frontmatter holds current state (`tags`); the body is a log of dated lines, appended to and never rewritten by tag
changes. Every wikilink in the body is an edge from the note.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from commonplace._links import Target, UnresolvedNote, is_named, links_to, resolve, resolve_target
from commonplace._repo import Commonplace
from commonplace._types import Note, RepoPath
from commonplace._utils import load_frontmatter

MARGINALIA_ROOT = Path(".commonplace/marginalia")

#: The sidecar format this release writes. Bump it, with an example in tests/resources/marginalia/, on any change.
MARGINALIA_VERSION = 1


@dataclass(frozen=True)
class Sidecar:
    """One note's marginalia: its tags, and the log of what's been said about it."""

    node: Path  # The annotated note, relative to the root
    ref: str | None = None  # The commit that last changed the note when it was last annotated
    tags: list[str] = field(default_factory=list)
    body: str = ""

    def tagged(self, *tags: str) -> "Sidecar":
        """This sidecar with `tags` added, after those it has, each once."""
        return replace(self, tags=list(dict.fromkeys([*self.tags, *tags])))

    def untagged(self, *tags: str) -> "Sidecar":
        """This sidecar without `tags`."""
        return replace(self, tags=[tag for tag in self.tags if tag not in tags])

    @property
    def edges(self) -> list[str]:
        """Every wikilink target in the body, in order: each is an edge from this note, prose or not."""
        return _WIKILINK_TARGET.findall(self.body)

    def linked(self, target: Target, why: str, on: date) -> "Sidecar":
        """This sidecar with an edge to `target` appended as a dated line."""
        line = f"- {on.isoformat()} [[{target}]]" + (f" {why}" if why else "")
        body = self.body if not self.body or self.body.endswith("\n") else self.body + "\n"
        return replace(self, body=f"{body}{line}\n")

    def unlinked(self, target: Target) -> tuple["Sidecar", int]:
        """This sidecar without the body lines that link to exactly `target`, and how many went."""
        marker = f"[[{target}]]"
        kept = [line for line in self.body.splitlines(keepends=True) if marker not in line]
        removed = len(self.body.splitlines(keepends=True)) - len(kept)
        return replace(self, body="".join(kept)), removed


_WIKILINK_TARGET = re.compile(r"\[\[([^[\]\n]+)]]")


def sidecar_path(node: Path) -> Path:
    """Where a note's sidecar lives, relative to the root."""
    return MARGINALIA_ROOT / node


def read_sidecar(root: Path, node: Path) -> Sidecar:
    """The note's sidecar, or an empty one if nothing has been said about it."""
    path = root / sidecar_path(node)
    if not path.exists():
        return Sidecar(node=node)
    metadata, body = load_frontmatter(path.read_text())
    version = metadata.get("marginalia", MARGINALIA_VERSION)
    if version > MARGINALIA_VERSION:
        raise ValueError(f"'{path}' is marginalia v{version}, newer than this release's v{MARGINALIA_VERSION}")
    return Sidecar(node=node, ref=metadata.get("ref"), tags=list(metadata.get("tags") or []), body=body)


def tagged(root: Path, tag: str) -> set[Path]:
    """Every note whose marginalia carry `tag`."""
    shadow = root / MARGINALIA_ROOT
    nodes = (path.relative_to(shadow) for path in shadow.rglob("*.md"))
    return {node for node in nodes if tag in read_sidecar(root, node).tags}


def tag(repo: Commonplace, spec: str, tags: list[str]) -> list[Path]:
    """Tag the notes `spec` names, committing as the user; returns the notes."""
    return _retag(repo, spec, lambda sidecar: sidecar.tagged(*tags), f"Tag {spec}: {', '.join(tags)}")


def untag(repo: Commonplace, spec: str, tags: list[str]) -> list[Path]:
    """Remove tags from the notes `spec` names, committing as the user; returns the notes."""
    return _retag(repo, spec, lambda sidecar: sidecar.untagged(*tags), f"Untag {spec}: {', '.join(tags)}")


def notes_named(repo: Commonplace, spec: str) -> list[Path]:
    """The whole notes `spec` names; a span is refused, since a sidecar speaks for a whole note."""
    if "#" in spec:
        raise UnresolvedNote(f"'{spec}' names a span; marginalia belong to whole notes")
    return resolve(spec, list(repo.paths()))


def link(repo: Commonplace, from_spec: str, to_spec: str, why: str, on: date | None = None) -> Target:
    """Add an edge from a whole note to a note or a span in one, committing as the user; returns the target."""
    files = list(repo.paths())
    if "#" in from_spec:
        raise UnresolvedNote(f"'{from_spec}' names a span; marginalia belong to whole notes")
    source = resolve_target(from_spec, repo.root, files).note
    target = resolve_target(to_spec, repo.root, files)
    today = date.today()  # noqa: DTZ011 - the user's local day, as the journal's
    sidecar = read_sidecar(repo.root, source).linked(target, why, on or today)
    write_sidecar(repo, replace(sidecar, ref=repo.make_repo_path(source).ref))
    repo.commit(f"Link {from_spec} to {target}", auto_index=False, as_user=True)
    return target


def unlink(repo: Commonplace, from_spec: str, to_spec: str) -> int:
    """Remove a note's edges to exactly `to_spec`'s target, committing as the user; returns how many went."""
    files = list(repo.paths())
    source = resolve_target(from_spec, repo.root, files).note
    target = resolve_target(to_spec, repo.root, files)
    sidecar, removed = read_sidecar(repo.root, source).unlinked(target)
    if not removed:
        raise ValueError(f"'{from_spec}' has no link to {target}")
    write_sidecar(repo, sidecar)
    repo.commit(f"Unlink {from_spec} from {target}", auto_index=False, as_user=True)
    return removed


def _retag(repo: Commonplace, spec: str, change: Callable[[Sidecar], Sidecar], message: str) -> list[Path]:
    nodes = notes_named(repo, spec)
    for node in nodes:
        sidecar = change(read_sidecar(repo.root, node))
        write_sidecar(repo, replace(sidecar, ref=repo.make_repo_path(node).ref))
    repo.commit(message, auto_index=False, as_user=True)
    return nodes


@dataclass(frozen=True)
class Backlink:
    """A note that links to another, and where: its marginalia line, or the line of its own text."""

    source: Path
    context: str


def backlinks(repo: Commonplace, spec: str, include_hidden: bool = False) -> list[Backlink]:
    """What links to the note `spec` names: edges in other notes' marginalia, then links in notes' own text."""
    [note] = notes_named(repo, spec)
    found = []
    shadow = repo.root / MARGINALIA_ROOT
    for path in sorted(shadow.rglob("*.md")):
        source = path.relative_to(shadow)
        for line in read_sidecar(repo.root, source).body.splitlines():
            names = (target.split("#")[0] for target in _WIKILINK_TARGET.findall(line))
            if any(is_named(note, name) for name in names):
                found.append(Backlink(source, line))
    found += [Backlink(link.source, f"line {link.line}") for link in links_to(note, repo.root, list(repo.paths()))]
    hidden = set() if include_hidden else tagged(repo.root, "hidden")
    return [backlink for backlink in found if backlink.source not in hidden]


def write_sidecar(repo: Commonplace, sidecar: Sidecar) -> None:
    """Save the sidecar for the repo's next commit."""
    metadata: dict = {"marginalia": MARGINALIA_VERSION}
    if sidecar.ref:
        metadata["ref"] = sidecar.ref
    metadata["tags"] = sidecar.tags
    repo.save(Note(RepoPath(sidecar_path(sidecar.node)), sidecar.body, metadata))
