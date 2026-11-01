"""Find the links in a repository's markdown, and check that they land somewhere."""

import fnmatch
import os
import re
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token
from mdit_py_plugins.front_matter import front_matter_plugin

from commonplace._utils import load_frontmatter

# Directories whose markdown is not a source of repository references.
SKIPPED_ROOTS: tuple[str, ...] = ("chats",)


class LinkKind(StrEnum):
    """Where a target is measured from, which is the only thing that varies."""

    PATH = "path"  # Relative to the file it is written in
    CITATION = "citation"  # Relative to the repository root, wherever it appears
    WIKILINK = "wikilink"  # Names a note rather than a location


@dataclass(frozen=True)
class Link:
    """A reference, as written, at a known place in a known file."""

    source: Path  # Relative to repo root
    line: int  # 1-based
    target: str  # Raw, as written: still percent-encoded, may carry a fragment
    kind: LinkKind


@dataclass(frozen=True)
class BrokenLink:
    """A reference that lands nowhere, and where it probably meant to."""

    link: Link
    reason: str
    suggestion: Path | None = None


# --- Extraction -------------------------------------------------------------

_EXTERNAL_SCHEME = re.compile(r"\A[a-z][a-z0-9+.-]*:", re.IGNORECASE)
_HTML_ATTRIBUTE = re.compile(r"""\b(?:href|src)[ \t]*=[ \t]*("[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
_WIKILINK = re.compile(r"\[\[[^[\]\n]+]]")


def _wikilink(state: StateInline, silent: bool) -> bool:
    """Consume a `[[page]]` as one `wikilink` token, pushing nothing when markdown-it is only looking ahead."""
    match = _WIKILINK.match(state.src, state.pos)
    if not match:
        return False
    if not silent:
        state.push("wikilink", "", 0).content = match.group()
    state.pos = match.end()
    return True


# CommonMark, taught the two syntaxes we care about that it does not have (front
# matter only so that it is skipped: `load_frontmatter` is what reads it), minus
# two conveniences: markdown-it percent-encodes destinations, which would have
# reports saying a%20note.md where the file says a note.md, and it decides for
# itself which schemes are safe, which is _is_repo_reference's job.
_MARKDOWN = MarkdownIt("commonmark").use(front_matter_plugin)
_MARKDOWN.inline.ruler.push("wikilink", _wikilink)
_MARKDOWN.normalizeLink = lambda url: url  # type: ignore[method-assign]
_MARKDOWN.validateLink = lambda url: True  # type: ignore[method-assign]


def _positioned(rule: Callable[[StateInline, bool], bool]) -> Callable[[StateInline, bool], bool]:
    """`rule`, stamping each token it pushes with the offset into its block's source where the token starts."""

    def stamped(state: StateInline, silent: bool) -> bool:
        start, pushed = state.pos, len(state.tokens)
        matched = rule(state, silent)
        for token in state.tokens[pushed:]:
            token.meta.setdefault("pos", start)  # Tokens nested inside this one keep their own
        return matched

    return stamped


# markdown-it maps lines only as far as the block, so inline tokens need their own offsets.
for _rule in list(_MARKDOWN.inline.ruler.__rules__):
    _MARKDOWN.inline.ruler.at(_rule.name, _positioned(_rule.fn))


def _line(block: Token, offset: int) -> int:
    """The 1-based line of `offset` into a block's source, which keeps the block's line breaks."""
    return (block.map[0] if block.map else 0) + block.content.count("\n", 0, offset) + 1


def _locate(lines: list[str], needle: str) -> int:
    """The first 1-based line holding `needle`."""
    return next((i + 1 for i, line in enumerate(lines) if needle in line), 1)


def _html_targets(html: str) -> Iterator[tuple[int, str]]:
    """The `href` and `src` attributes in a piece of raw HTML, each with its offset."""
    for attribute in _HTML_ATTRIBUTE.finditer(html):
        if target := attribute.group(1).strip("\"'"):
            yield attribute.start(), target


def _strings(value: object) -> Iterator[str]:
    """Every string at or under a frontmatter value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _frontmatter_citations(text: str, lines: list[str]) -> Iterator[tuple[int, str, LinkKind]]:
    """The paths an artefact's frontmatter cites under any `source*` key."""
    metadata, _ = load_frontmatter(text)
    for key, value in metadata.items():
        if str(key).startswith("source"):
            for target in _strings(value):
                if target.endswith(".md"):
                    # Frontmatter comes first, so the first line to mention a path is the one that cites it.
                    yield _locate(lines, target), target, LinkKind.CITATION


def _inline_references(child: Token, block: Token) -> Iterator[tuple[int, str, LinkKind]]:
    """The references in one inline token, whichever syntax carried it."""
    start = child.meta.get("pos", 0)
    if child.type == "wikilink":
        # `page#section` names `page`.
        if target := child.content.strip("[]").split("#")[0].strip():
            yield _line(block, start), target, LinkKind.WIKILINK
    elif child.type == "html_inline":
        for offset, target in _html_targets(child.content):
            yield _line(block, start + offset), target, LinkKind.PATH
    # Reference, collapsed and shortcut links arrive already resolved to their
    # definition, so every one of them looks inline by here.
    elif (attribute := {"link_open": "href", "image": "src"}.get(child.type)) and (
        target := str(child.attrGet(attribute) or "")
    ):
        yield _line(block, start), target, LinkKind.PATH


def _references(tokens: list[Token]) -> Iterator[tuple[int, str, LinkKind]]:
    """Every reference in the token stream, now that the parser knows every syntax we use."""
    for token in tokens:
        if token.type == "html_block":
            for offset, target in _html_targets(token.content):
                yield _line(token, offset), target, LinkKind.PATH
        elif token.type == "inline":
            for child in token.children or []:
                yield from _inline_references(child, token)


def _is_repo_reference(target: str) -> bool:
    """True if `target` could name something in this repository."""
    target = target.strip()
    if not target or target.startswith(("#", "//")):
        return False
    return not _EXTERNAL_SCHEME.match(target)


def extract_links(text: str, *, source: Path) -> list[Link]:
    """Every reference in `text` that could point into the repository, in document order."""
    lines = text.split("\n")
    found = [*_frontmatter_citations(text, lines), *_references(_MARKDOWN.parse(text))]
    links = []
    for line, target, kind in sorted(found, key=lambda item: item[0]):
        if _is_repo_reference(target := target.strip()):
            links.append(Link(source=source, line=line, target=target, kind=kind))
    return links


# --- Resolution -------------------------------------------------------------


def _index(files: Collection[Path]) -> dict[str, list[Path]]:
    """Every file by name and by stem."""
    index: dict[str, list[Path]] = {}
    for path in files:
        for key in {path.name, path.stem}:
            index.setdefault(key, []).append(path)
    return index


def _unique(index: dict[str, list[Path]], name: str) -> Path | None:
    """The one file called `name`, if there is exactly one."""
    found = index.get(name, [])
    return found[0] if len(found) == 1 else None


def is_named(path: Path, name: str) -> bool:
    """True if `name` is how a wikilink would write `path`: its tail, or from `/` its whole path, either extension."""
    return any(
        f"/{written}" == name or written == name or written.endswith(f"/{name}")
        for written in (path.as_posix(), path.with_suffix("").as_posix())
    )


class UnresolvedNote(ValueError):
    """A spec that names no note, or more than one where one was meant."""


def resolve(spec: str, files: Collection[Path]) -> list[Path]:
    """The notes a wikilink-style spec names: exactly one, or every match of a glob, or `UnresolvedNote`.

    Stricter than a link check, which accepts any note of the name: a command that writes must know which.
    """
    name = spec.removeprefix("[[").removesuffix("]]").split("#")[0].strip()
    notes = sorted(path for path in files if path.suffix == ".md")
    if "*" in name:
        matched = [path for path in notes if fnmatch.fnmatchcase(path.as_posix(), name.lstrip("/"))]
        if not matched:
            raise UnresolvedNote(f"'{spec}' matches no note")
        return matched
    found = [path for path in notes if is_named(path, name)]
    if not found:
        raise UnresolvedNote(f"'{spec}' names no note")
    if len(found) > 1:
        candidates = "\n".join(f"  /{path.with_suffix('').as_posix()}" for path in found)
        raise UnresolvedNote(f"'{spec}' names {len(found)} notes; say which:\n{candidates}")
    return found


@dataclass(frozen=True)
class Target:
    """One note, and optionally a span in it: a heading's text, or a quoted phrase."""

    note: Path  # Relative to the root
    fragment: str = ""

    def __str__(self) -> str:
        """Rooted and without `.md`, so a later note of the same name can't make it ambiguous."""
        rooted = "/" + self.note.with_suffix("").as_posix()
        return f"{rooted}#{self.fragment}" if self.fragment else rooted


def resolve_target(spec: str, root: Path, files: Collection[Path]) -> Target:
    """The one note `spec` names, with its span checked against the note: `#Heading` or `#"exact phrase"`."""
    if "*" in spec:
        raise UnresolvedNote(f"'{spec}' is a glob; a link joins one note to one note")
    [note] = resolve(spec, files)
    _, _, fragment = spec.removeprefix("[[").removesuffix("]]").partition("#")
    if fragment and not _has_span(root / note, fragment):
        raise UnresolvedNote(f"'{spec}': no such heading or phrase in /{note.with_suffix('').as_posix()}")
    return Target(note, fragment)


def _has_span(path: Path, fragment: str) -> bool:
    """Whether the note has a heading reading `fragment` exactly, or for `"phrase"`, contains the phrase."""
    text = path.read_text(errors="replace")
    if len(fragment) > 1 and fragment.startswith('"') and fragment.endswith('"'):
        return fragment[1:-1] in text
    return any(line.lstrip("#").strip() == fragment for line in text.splitlines() if line.startswith("#"))


def _reason_broken(link: Link, root: Path, index: dict[str, list[Path]], present: set[Path]) -> str:
    """Why `link` lands nowhere — empty if it lands somewhere."""
    if link.kind is LinkKind.WIKILINK:
        # A wikilink names a note, not a location: any note with that name will do.
        found = any(is_named(path, link.target) for path in index.get(Path(link.target).name, []))
        return "" if found else "no note with that name"

    if not unquote(link.target.split("#")[0].split("?")[0]):
        return "empty target"
    candidate = _landing(link, root)
    if not candidate.is_relative_to(root):
        return "outside the repository"
    if candidate.relative_to(root) in present:
        return ""
    return "on disk but not in the repository" if candidate.exists() else "no such file"


def _landing(link: Link, root: Path) -> Path:
    """The absolute path a path link or citation points at; citations are written from the root, wherever they are."""
    target = unquote(link.target.split("#")[0].split("?")[0])
    root_relative = link.kind is LinkKind.CITATION or target.startswith("/")
    base = root if root_relative else root / link.source.parent
    return Path(os.path.normpath(base / target.lstrip("/")))


def links_from(note: Path, root: Path, files: Collection[Path]) -> list[tuple[Link, Path]]:
    """Each link in `note`'s own text that lands on exactly one note among `files`, with where it lands."""
    notes = [path for path in files if path.suffix == ".md"]
    present = set(files)
    found = []
    for link in extract_links((root / note).read_text(errors="replace"), source=note):
        if link.kind is LinkKind.WIKILINK:
            named = [path for path in notes if is_named(path, link.target)]
            lands = named[0] if len(named) == 1 else None
        else:
            candidate = _landing(link, root)
            inside = candidate.is_relative_to(root) and candidate.relative_to(root) in present
            lands = candidate.relative_to(root) if inside else None
        if lands is not None:
            found.append((link, lands))
    return found


def links_to(note: Path, root: Path, files: Collection[Path], *, skip: Collection[str] = SKIPPED_ROOTS) -> list[Link]:
    """Every link in the markdown among `files` that lands on `note`, in file order; chats quote, so are skipped."""
    found = []
    for path in sorted(files):
        if path.suffix != ".md" or path.parts[0] in tuple(skip) or path == note:
            continue
        for link in extract_links((root / path).read_text(errors="replace"), source=path):
            if link.kind is LinkKind.WIKILINK:
                lands = is_named(note, link.target)
            else:
                lands = unquote(link.target.split("#")[0]) != "" and _landing(link, root) == root / note
            if lands:
                found.append(link)
    return found


def check_links(
    root: Path,
    files: Collection[Path],
    *,
    skip: Collection[str] = SKIPPED_ROOTS,
) -> list[BrokenLink]:
    """Every reference in the markdown among `files` that lands on none of them, nor on a directory holding one."""
    index = _index(files)
    present = set(files) | {parent for path in files for parent in path.parents}
    skipped = tuple(skip)
    broken = []
    for path in sorted(files):
        if path.suffix != ".md" or path.parts[0] in skipped:
            continue
        for link in extract_links((root / path).read_text(errors="replace"), source=path):
            if reason := _reason_broken(link, root, index, present):
                name = Path(unquote(link.target.split("#")[0])).name
                broken.append(BrokenLink(link=link, reason=reason, suggestion=_unique(index, name)))
    return broken


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
