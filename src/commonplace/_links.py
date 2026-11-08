"""Find the links in markdown, as written; where they land is the graph's business (`_graph`)."""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token
from mdit_py_plugins.front_matter import front_matter_plugin

from commonplace._utils import load_frontmatter


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
        # `page#section` names a span in `page`; `#section` alone is this note's own.
        target = child.content.strip("[]").strip()
        if target.split("#")[0].strip():
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


@dataclass(frozen=True)
class Target:
    """One note, and optionally a span in it: a heading's text, or a quoted phrase."""

    note: Path  # Relative to the root
    fragment: str = ""

    def __str__(self) -> str:
        """Rooted and without `.md`, so a later note of the same name can't make it ambiguous."""
        rooted = "/" + self.note.with_suffix("").as_posix()
        return f"{rooted}#{self.fragment}" if self.fragment else rooted
