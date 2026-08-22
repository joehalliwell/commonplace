"""
Find links in markdown, and check that the ones pointing into the repository resolve.

Two separate jobs, deliberately kept apart:

- **Extraction** is a property of a piece of text. `extract_links` finds every
  reference a reader could follow, in whatever form it was written: inline and
  reference-style markdown links, images, wikilinks, raw HTML, and the bare
  repo-relative paths that gatherings and distillations cite their sources with.
- **Resolution** is a property of the repository the text sits in. `check_links`
  walks a commonplace and reports the references that no longer land anywhere.

Keeping the seam there means the same extractor can answer "what does this file
point at?" for a backlink graph or a link suggester, not just "what is broken?".

Markdown itself is parsed by markdown-it — already in the tree under `mdformat`
— rather than by hand. Link syntax has more corners than it looks (balanced
parens in a destination, titles in three quotings, reference definitions
resolved from elsewhere in the file, code spans that must not be read as
prose), and a CommonMark parser is not a thing worth owning a copy of. What is
left here is the part no parser knows about: wikilinks, and the citation forms
this project invented.

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
    """How a reference was written. Affects how it resolves, and how it reads in a report."""

    # No REFERENCE: the parser resolves reference-style links to their
    # definition, and by the time we see one it is indistinguishable from inline.
    INLINE = "inline"
    IMAGE = "image"
    WIKILINK = "wikilink"
    HTML = "html"
    CITATION = "citation"


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
_FRONTMATTER = re.compile(r"\A---\n(?P<body>.*?)\n---(?:\n|\Z)", re.DOTALL)
_YAML_PATH = re.compile(
    r"""^[ \t]*(?:-[ \t]*|[\w.-]+:[ \t]*)(?P<quote>["']?)(?P<path>[^\s"']+\.md)(?P=quote)[ \t]*$""", re.MULTILINE
)
_DATED_CITATION = re.compile(r"\(\d{4}-\d{2}-\d{2},[ \t]*(?P<path>[^)\s]+\.md)\)")


def _parser() -> MarkdownIt:
    """
    CommonMark, with the two conveniences we do not want.

    Destinations are reported exactly as written — markdown-it would otherwise
    percent-encode them, and a report that says `a%20note.md` when the file says
    `a note.md` is a report you have to decode before you can act on it. Which
    schemes count as ours is decided in `_is_repo_reference`, not by the parser.
    """
    md = MarkdownIt("commonmark")
    md.normalizeLink = lambda url: url  # type: ignore[method-assign]
    md.validateLink = lambda url: True  # type: ignore[method-assign]
    return md


_MARKDOWN = _parser()


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
    start, end = span[0], min(span[1], len(lines))
    for i in range(start, end):
        if needle in lines[i]:
            return i + 1
    return start + 1


def _attribute(token: Token, name: str) -> str:
    """A token attribute as text — markdown-it types them loosely, but a URL is a string."""
    value = token.attrGet(name)
    return str(value) if value is not None else ""


def _token_links(tokens: list[Token], lines: list[str]) -> Iterator[tuple[int, str, LinkKind]]:
    """Links, images and raw HTML, as markdown-it sees them."""
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        for child in token.children:
            if child.type == "link_open":
                # Reference, collapsed and shortcut links arrive already resolved
                # to their definition, so every one of them looks inline by here.
                target = _attribute(child, "href")
                if target:
                    yield _locate(lines, token.map, target), target, LinkKind.INLINE
            elif child.type == "image":
                target = _attribute(child, "src")
                if target:
                    yield _locate(lines, token.map, target), target, LinkKind.IMAGE
            elif child.type == "html_inline":
                for attribute in _HTML_ATTRIBUTE.finditer(child.content):
                    target = attribute.group(1).strip("\"'")
                    if target:
                        yield _locate(lines, token.map, target), target, LinkKind.HTML
    for token in tokens:
        if token.type == "html_block" and token.map:
            for offset, line in enumerate(lines[token.map[0] : min(token.map[1], len(lines))]):
                for attribute in _HTML_ATTRIBUTE.finditer(line):
                    target = attribute.group(1).strip("\"'")
                    if target:
                        yield token.map[0] + offset + 1, target, LinkKind.HTML


def _pattern_links(prose: list[str]) -> Iterator[tuple[int, str, LinkKind]]:
    """Wikilinks and inline dated citations: prose forms no CommonMark parser knows."""
    for number, line in enumerate(prose, start=1):
        for match in _WIKILINK.finditer(line):
            # `page|alias` and `page#section` both name `page`.
            target = match.group("body").split("|")[0].split("#")[0].strip()
            if target:
                yield number, target, LinkKind.WIKILINK
        for match in _DATED_CITATION.finditer(line):
            yield number, match.group("path"), LinkKind.CITATION


def _frontmatter_citations(text: str) -> Iterator[tuple[int, str, LinkKind]]:
    """
    Source paths in frontmatter.

    A gathering lists the passages a distillation rests on. These are the
    references that matter most — they are its evidence — and until recently
    they were the ones nothing checked.
    """
    frontmatter = _FRONTMATTER.match(text)
    if not frontmatter:
        return
    first_line = text[: frontmatter.start("body")].count("\n") + 1
    for match in _YAML_PATH.finditer(frontmatter.group("body")):
        line = first_line + frontmatter.group("body")[: match.start("path")].count("\n")
        yield line, match.group("path"), LinkKind.CITATION


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
    lines = text.split("\n")
    prose = _prose(text, tokens)

    found = list(_token_links(tokens, lines)) + list(_pattern_links(prose)) + list(_frontmatter_citations(text))
    links: dict[tuple[int, str], Link] = {}
    for line, target, kind in sorted(found, key=lambda item: item[0]):
        target = target.strip()
        if _is_repo_reference(target):
            links.setdefault((line, target), Link(source=source, line=line, target=target, kind=kind))
    return list(links.values())


# --- Resolution -------------------------------------------------------------


@dataclass
class _Corpus:
    """Everything the resolver needs to know about what exists."""

    root: Path
    by_name: dict[str, list[Path]]  # filename -> repo-relative paths
    by_stem: dict[str, list[Path]]  # filename without extension -> repo-relative paths

    @staticmethod
    def scan(root: Path) -> "_Corpus":
        by_name: dict[str, list[Path]] = {}
        by_stem: dict[str, list[Path]] = {}
        for path in _walk(root):
            by_name.setdefault(path.name, []).append(path)
            by_stem.setdefault(path.stem, []).append(path)
        return _Corpus(root=root, by_name=by_name, by_stem=by_stem)

    def unique(self, name: str) -> Path | None:
        """The one file with this name or stem, if there is exactly one."""
        for candidates in (self.by_name.get(name, []), self.by_stem.get(name, [])):
            if len(candidates) == 1:
                return candidates[0]
        return None


def _walk(root: Path) -> Iterator[Path]:
    """Every file in the repository, as repo-relative paths, skipping dot directories."""
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if not d.startswith(".")]
        for name in files:
            yield (Path(directory) / name).relative_to(root)


def resolve(link: Link, corpus: _Corpus) -> tuple[Path | None, str]:
    """
    Where `link` lands, and why it does not land anywhere if it does not.

    Returns a repo-relative path if the target exists, otherwise None and a reason.
    """
    if link.kind is LinkKind.WIKILINK:
        # Wikilinks name a note, not a location: any note with that name will do.
        found = corpus.unique(link.target) or corpus.unique(f"{link.target}.md")
        return (found, "") if found else (None, "no note with that name")

    target = unquote(link.target.split("#")[0].split("?")[0])
    if not target:
        return None, "empty target"

    # Citations are always written from the repository root, wherever they appear.
    if link.kind is LinkKind.CITATION or target.startswith("/"):
        candidate = corpus.root / target.lstrip("/")
    else:
        candidate = corpus.root / link.source.parent / target

    candidate = Path(os.path.normpath(candidate))
    if not candidate.is_relative_to(corpus.root):
        return None, "outside the repository"
    if not candidate.exists():
        return None, "no such file"
    return candidate.relative_to(corpus.root), ""


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


def find_links(root: Path, *, skip: Collection[str] = SKIPPED_ROOTS) -> Iterator[Link]:
    """
    Every reference the repository's own markdown makes, whether or not it lands.

    This is the graph: what points at what, before any judgement about which
    edges are still good.
    """
    skipped = tuple(skip)
    for path in sorted(_walk(root)):
        if path.suffix != ".md" or path.parts[0] in skipped:
            continue
        yield from extract_links((root / path).read_text(errors="replace"), source=path)


def check_links(root: Path, *, skip: Collection[str] = SKIPPED_ROOTS) -> list[BrokenLink]:
    """
    Every reference in the repository's own markdown that no longer lands anywhere.

    Where a file with the target's name exists somewhere else — which is what a
    rename looks like from here — the new location is offered as a suggestion.
    """
    corpus = _Corpus.scan(root)
    broken = []
    for link in find_links(root, skip=skip):
        found, reason = resolve(link, corpus)
        if found is None:
            name = Path(unquote(link.target.split("#")[0])).name
            broken.append(BrokenLink(link=link, reason=reason, suggestion=corpus.unique(name)))
    return broken
