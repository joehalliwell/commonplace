"""Find the links in a repository's markdown, and check that they land somewhere."""

import os
import re
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdformat_wikilink.mdit_wikilink_plugin import wikilink_plugin  # type: ignore[import-untyped]
from mdit_py_plugins.front_matter import front_matter_plugin

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
_YAML_PATH = re.compile(
    r"""^[ \t]*(?:-[ \t]*|[\w.-]+:[ \t]*)(?P<quote>["']?)(?P<path>[^\s"']+\.md)(?P=quote)[ \t]*$""", re.MULTILINE
)
_DATED_CITATION = re.compile(r"\(\d{4}-\d{2}-\d{2},[ \t]*(?P<path>[^)\s]+\.md)\)")

# CommonMark, taught the two syntaxes we care about that it does not have, minus
# two conveniences: markdown-it percent-encodes destinations, which would have
# reports saying a%20note.md where the file says a note.md, and it decides for
# itself which schemes are safe, which is _is_repo_reference's job.
_MARKDOWN = MarkdownIt("commonmark").use(wikilink_plugin).use(front_matter_plugin)
_MARKDOWN.normalizeLink = lambda url: url  # type: ignore[method-assign]
_MARKDOWN.validateLink = lambda url: True  # type: ignore[method-assign]


def _locate(lines: list[str], span: list[int] | None, needle: str) -> int:
    """The 1-based line holding `needle`, which markdown-it maps only as far as its block."""
    if span is None:
        return 1
    for i in range(span[0], min(span[1], len(lines))):
        if needle in lines[i]:
            return i + 1
    return span[0] + 1


def _html_targets(html: str) -> Iterator[str]:
    """The `href` and `src` attributes in a piece of raw HTML."""
    for attribute in _HTML_ATTRIBUTE.finditer(html):
        if target := attribute.group(1).strip("\"'"):
            yield target


def _frontmatter_citations(token: Token) -> Iterator[tuple[int, str, LinkKind]]:
    """The source paths a gathering lists in its frontmatter."""
    first_line = (token.map[0] if token.map else 0) + 2  # Past the opening `---`
    for match in _YAML_PATH.finditer(token.content):
        yield first_line + token.content[: match.start("path")].count("\n"), match.group("path"), LinkKind.CITATION


def _inline_references(child: Token, span: list[int] | None, lines: list[str]) -> Iterator[tuple[int, str, LinkKind]]:
    """The references in one inline token, whichever syntax carried it."""
    if child.type == "wikilink":
        # `page|alias` and `page#section` both name `page`.
        if target := child.content.strip("[]").split("|")[0].split("#")[0].strip():
            yield _locate(lines, span, child.content), target, LinkKind.WIKILINK
    elif child.type == "html_inline":
        for target in _html_targets(child.content):
            yield _locate(lines, span, target), target, LinkKind.PATH
    elif child.type == "text":
        for match in _DATED_CITATION.finditer(child.content):
            yield _locate(lines, span, match.group("path")), match.group("path"), LinkKind.CITATION
    # Reference, collapsed and shortcut links arrive already resolved to their
    # definition, so every one of them looks inline by here.
    elif (attribute := {"link_open": "href", "image": "src"}.get(child.type)) and (
        target := str(child.attrGet(attribute) or "")
    ):
        yield _locate(lines, span, target), target, LinkKind.PATH


def _references(tokens: list[Token], lines: list[str]) -> Iterator[tuple[int, str, LinkKind]]:
    """Every reference in the token stream, now that the parser knows every syntax we use."""
    for token in tokens:
        if token.type == "front_matter":
            yield from _frontmatter_citations(token)
        elif token.type == "html_block":
            for target in _html_targets(token.content):
                yield _locate(lines, token.map, target), target, LinkKind.PATH
        elif token.type == "inline":
            for child in token.children or []:
                yield from _inline_references(child, token.map, lines)


def _is_repo_reference(target: str) -> bool:
    """True if `target` could name something in this repository."""
    target = target.strip()
    if not target or target.startswith(("#", "//")):
        return False
    return not _EXTERNAL_SCHEME.match(target)


def extract_links(text: str, *, source: Path) -> list[Link]:
    """Every reference in `text` that could point into the repository, in document order."""
    found = list(_references(_MARKDOWN.parse(text), text.split("\n")))

    links: dict[tuple[int, str], Link] = {}
    for line, target, kind in sorted(found, key=lambda item: item[0]):
        if _is_repo_reference(target := target.strip()):
            links.setdefault((line, target), Link(source=source, line=line, target=target, kind=kind))
    return list(links.values())


# --- Resolution -------------------------------------------------------------


def _walk(root: Path) -> Iterator[Path]:
    """Every file in the repository, as repo-relative paths, skipping dot directories."""
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if not d.startswith(".")]
        for name in files:
            yield (Path(directory) / name).relative_to(root)


def _index(root: Path) -> dict[str, list[Path]]:
    """Every file by name and by stem."""
    index: dict[str, list[Path]] = {}
    for path in _walk(root):
        for key in {path.name, path.stem}:
            index.setdefault(key, []).append(path)
    return index


def _unique(index: dict[str, list[Path]], name: str) -> Path | None:
    """The one file called `name`, if there is exactly one."""
    found = index.get(name, [])
    return found[0] if len(found) == 1 else None


def _reason_broken(link: Link, root: Path, index: dict[str, list[Path]]) -> str:
    """Why `link` lands nowhere — empty if it lands somewhere."""
    if link.kind is LinkKind.WIKILINK:
        # A wikilink names a note, not a location: any note with that name will do.
        found = _unique(index, link.target) or _unique(index, f"{link.target}.md")
        return "" if found else "no note with that name"

    target = unquote(link.target.split("#")[0].split("?")[0])
    if not target:
        return "empty target"

    # Citations are written from the repository root, wherever they appear.
    root_relative = link.kind is LinkKind.CITATION or target.startswith("/")
    base = root if root_relative else root / link.source.parent
    candidate = Path(os.path.normpath(base / target.lstrip("/")))

    if not candidate.is_relative_to(root):
        return "outside the repository"
    return "" if candidate.exists() else "no such file"


def check_links(root: Path, *, skip: Collection[str] = SKIPPED_ROOTS) -> list[BrokenLink]:
    """Every reference in the repository's own markdown that lands nowhere."""
    index = _index(root)
    skipped = tuple(skip)
    broken = []
    for path in sorted(_walk(root)):
        if path.suffix != ".md" or path.parts[0] in skipped:
            continue
        for link in extract_links((root / path).read_text(errors="replace"), source=path):
            if reason := _reason_broken(link, root, index):
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
            suggestion = f" — moved to {item.suggestion}?" if item.suggestion else ""
            lines.append(f"  line {item.link.line}: {item.link.target} ({item.reason}){suggestion}")
        summaries.append("\n".join(lines))
    return summaries
