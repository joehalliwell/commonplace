"""
Find links in markdown, and check that the ones pointing into the repository resolve.

Two separate jobs, deliberately kept apart:

- **Extraction** is a property of a piece of text. `extract_links` finds every
  reference a reader could follow, in whatever form it was written: inline and
  reference-style markdown links, images, wikilinks, raw HTML, and the bare
  repo-relative paths that gatherings and distillations cite their sources with.
- **Resolution** is a property of the repository the text sits in. `check_links`
  walks a commonplace and reports the references that no longer land anywhere.

Markdown itself is parsed by markdown-it — already in the tree under `mdformat`
— rather than by hand. Link syntax has more corners than it looks, and a
CommonMark parser is not a thing worth owning a copy of. What is left here is
the part no parser knows about: wikilinks, and the citation forms this project
invented.

Two things this deliberately does not do. It does not check external URLs —
that needs the network, and a checker that is slow and flaky is a checker you
stop running. And it does not read `chats/**`: transcripts are primitives,
quoted verbatim, and a link inside one is content the model or the user wrote,
not a claim about this repository. Chats are link *targets*, never link sources.
"""

import os
import re
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.token import Token

# Directories whose markdown is not a source of repository references.
SKIPPED_ROOTS: tuple[str, ...] = ("chats",)


class LinkKind(StrEnum):
    """
    How a reference resolves.

    Only three, because only three things happen. How a link was *written* —
    inline, reference-style, an image, raw HTML — makes no difference once it
    has been read, so it is not recorded.
    """

    PATH = "path"  # Relative to the file it is written in
    CITATION = "citation"  # Relative to the repository root, wherever it appears
    WIKILINK = "wikilink"  # Names a note rather than a location


@dataclass(frozen=True)
class Link:
    """A single reference, as written, at a known place in a known file."""

    source: Path  # Relative to repo root
    line: int  # 1-based
    target: str  # Raw, as written: still percent-encoded, may carry a fragment
    kind: LinkKind


@dataclass(frozen=True)
class BrokenLink:
    """A reference that does not land anywhere, and our best guess at where it meant to."""

    link: Link
    reason: str
    suggestion: Path | None = None


# --- Extraction -------------------------------------------------------------

_EXTERNAL_SCHEME = re.compile(r"\A[a-z][a-z0-9+.-]*:", re.IGNORECASE)
_CODE_SPAN = re.compile(r"(?P<ticks>`+)(?P<body>.+?)(?P=ticks)", re.DOTALL)
_HTML_ATTRIBUTE = re.compile(r"""\b(?:href|src)[ \t]*=[ \t]*("[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
_WIKILINK = re.compile(r"\[\[(?P<body>[^\]]+)\]\]")
_YAML_PATH = re.compile(
    r"""\A[ \t]*(?:-[ \t]*|[\w.-]+:[ \t]*)(?P<quote>["']?)(?P<path>[^\s"']+\.md)(?P=quote)[ \t]*\Z"""
)
_DATED_CITATION = re.compile(r"\(\d{4}-\d{2}-\d{2},[ \t]*(?P<path>[^)\s]+\.md)\)")

# CommonMark, minus two conveniences. markdown-it percent-encodes destinations,
# which would have reports saying a%20note.md where the file says a note.md; and
# it decides for itself which schemes are safe, which is _is_repo_reference's job.
_MARKDOWN = MarkdownIt("commonmark")
_MARKDOWN.normalizeLink = lambda url: url  # type: ignore[method-assign]
_MARKDOWN.validateLink = lambda url: True  # type: ignore[method-assign]


def _blank(text: str) -> str:
    """Replace `text` with spaces, preserving length and line structure."""
    return "".join("\n" if char == "\n" else " " for char in text)


def _prose(text: str, tokens: list[Token]) -> list[str]:
    """
    The lines of `text` with all code blanked out, for the patterns markdown-it does not know.

    A note *about* markdown, showing `[[a wikilink]]` as an example, is not
    claiming that page exists.
    """
    lines = text.split("\n")
    for token in tokens:
        if token.type in ("fence", "code_block") and token.map:
            for i in range(token.map[0], min(token.map[1], len(lines))):
                lines[i] = _blank(lines[i])
    return _CODE_SPAN.sub(lambda m: _blank(m.group()), "\n".join(lines)).split("\n")


def _locate(lines: list[str], span: list[int] | None, needle: str) -> int:
    """
    The 1-based line holding `needle`, searched within the block at `span`.

    markdown-it maps blocks, not the inline tokens inside them, so for anything
    longer than a one-line paragraph the block start is not good enough to go
    and fix the link by. Finding the text again is cruder than tracking offsets
    through the parse, and it does not go wrong in ways that need explaining.
    """
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


def _token_links(tokens: list[Token], lines: list[str]) -> Iterator[tuple[int, str, LinkKind]]:
    """Links, images and raw HTML, as markdown-it sees them."""
    for token in tokens:
        if token.type == "html_block":
            for target in _html_targets(token.content):
                yield _locate(lines, token.map, target), target, LinkKind.PATH
        if token.type != "inline":
            continue
        for child in token.children or []:
            # Reference, collapsed and shortcut links arrive already resolved to
            # their definition, so every one of them looks inline by here.
            if child.type == "html_inline":
                for target in _html_targets(child.content):
                    yield _locate(lines, token.map, target), target, LinkKind.PATH
                continue
            attribute = {"link_open": "href", "image": "src"}.get(child.type)
            if attribute and (target := str(child.attrGet(attribute) or "")):
                yield _locate(lines, token.map, target), target, LinkKind.PATH


def _pattern_links(prose: list[str]) -> Iterator[tuple[int, str, LinkKind]]:
    """
    Wikilinks, and the citations this project invented.

    A gathering lists the passages a distillation rests on, in frontmatter and
    inline as `(<date>, <path>)`. Those are the references that matter most —
    they are its evidence — and until recently they were the ones nothing checked.
    """
    in_frontmatter = bool(prose) and prose[0].strip() == "---"
    for number, line in enumerate(prose, start=1):
        if in_frontmatter:
            if number > 1 and line.strip() == "---":
                in_frontmatter = False
            elif match := _YAML_PATH.match(line):
                yield number, match.group("path"), LinkKind.CITATION
            continue
        for match in _WIKILINK.finditer(line):
            # `page|alias` and `page#section` both name `page`.
            if target := match.group("body").split("|")[0].split("#")[0].strip():
                yield number, target, LinkKind.WIKILINK
        for match in _DATED_CITATION.finditer(line):
            yield number, match.group("path"), LinkKind.CITATION


def _is_repo_reference(target: str) -> bool:
    """True if `target` could name something in this repository."""
    target = target.strip()
    if not target or target.startswith(("#", "//")):
        return False
    return not _EXTERNAL_SCHEME.match(target)


def extract_links(text: str, *, source: Path) -> list[Link]:
    """
    Every reference in `text` that could point into the repository, in document order.

    External URLs, pure fragments and code samples are left out. References that
    repeat the same target on the same line are reported once.
    """
    tokens = _MARKDOWN.parse(text)
    found = list(_token_links(tokens, text.split("\n"))) + list(_pattern_links(_prose(text, tokens)))

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
    """Every file by name and by stem: what wikilinks resolve through, and what renames are guessed from."""
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
    """
    Every reference in the repository's own markdown that no longer lands anywhere.

    Where a file with the target's name exists somewhere else — which is what a
    rename looks like from here — the new location is offered as a suggestion.
    """
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
    """One report per file, listing what no longer resolves and where it probably went."""
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
