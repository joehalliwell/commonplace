"""Marginalia: what's been said about a note since, kept in a shadow tree beside it rather than in it.

A note's sidecar sits at its path under `.commonplace/marginalia/`. Notes owned by another system of record
are rewritten on every fetch, and primitives are immutable, so this is the one place to tag any note.
Frontmatter holds current state (`tags`); the body is a log, appended to and never rewritten by tag changes.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from commonplace._links import UnresolvedNote, resolve
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
    """The whole notes `spec` names; a span is refused, since tags describe whole notes."""
    if "#" in spec:
        raise UnresolvedNote(f"'{spec}' names a span; tags apply to whole notes")
    return resolve(spec, list(repo.paths()))


def _retag(repo: Commonplace, spec: str, change: Callable[[Sidecar], Sidecar], message: str) -> list[Path]:
    nodes = notes_named(repo, spec)
    for node in nodes:
        sidecar = change(read_sidecar(repo.root, node))
        write_sidecar(repo, replace(sidecar, ref=repo.make_repo_path(node).ref))
    repo.commit(message, auto_index=False, as_user=True)
    return nodes


def write_sidecar(repo: Commonplace, sidecar: Sidecar) -> None:
    """Save the sidecar for the repo's next commit."""
    metadata: dict = {"marginalia": MARGINALIA_VERSION}
    if sidecar.ref:
        metadata["ref"] = sidecar.ref
    metadata["tags"] = sidecar.tags
    repo.save(Note(RepoPath(sidecar_path(sidecar.node)), sidecar.body, metadata))
