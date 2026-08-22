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

# Directories whose markdown is not a source of repository references.
SKIPPED_ROOTS: tuple[str, ...] = ("chats",)


class LinkKind(StrEnum):
    """How a reference was written. Affects how it resolves, and how it reads in a report."""

    INLINE = "inline"
    REFERENCE = "reference"
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
_FENCE = re.compile(r"\A {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)\Z")
_CODE_SPAN = re.compile(r"(?P<ticks>`+)(?P<body>.+?)(?P=ticks)", re.DOTALL)
_DEFINITION = re.compile(r"^ {0,3}\[(?P<label>[^\]^][^\]]*)\]:[ \t]*(?P<dest><[^>\n]*>|\S+)", re.MULTILINE)
_FOOTNOTE_DEFINITION = re.compile(r"^ {0,3}\[\^[^\]]*\]:", re.MULTILINE)
_HTML_TAG = re.compile(r"<[a-zA-Z][^>]*>", re.DOTALL)
_HTML_ATTRIBUTE = re.compile(r"""\b(?:href|src)[ \t]*=[ \t]*("[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
_FRONTMATTER = re.compile(r"\A---\n(?P<body>.*?)\n---(?:\n|\Z)", re.DOTALL)
_YAML_PATH = re.compile(
    r"""^[ \t]*(?:-[ \t]*|[\w.-]+:[ \t]*)(?P<quote>["']?)(?P<path>[^\s"']+\.md)(?P=quote)[ \t]*$""", re.MULTILINE
)
_DATED_CITATION = re.compile(r"\(\d{4}-\d{2}-\d{2},[ \t]*(?P<path>[^)\s]+\.md)\)")


def _blank(text: str) -> str:
    """Replace `text` with spaces, preserving length and line structure."""
    return "".join("\n" if char == "\n" else " " for char in text)


def _mask_code(text: str) -> str:
    """
    Blank out fenced code blocks and inline code spans, preserving all offsets.

    A note about markdown that shows `[a](b.md)` as an example is not making a
    claim that `b.md` exists.
    """
    lines = text.split("\n")
    fence: str | None = None
    for i, line in enumerate(lines):
        match = _FENCE.match(line)
        if fence is None:
            if match:
                fence = match.group("fence")
                lines[i] = _blank(line)
            continue
        # Inside a fence: only a bare fence of the same character, at least as long, closes it.
        if (
            match
            and match.group("fence")[0] == fence[0]
            and len(match.group("fence")) >= len(fence)
            and not match.group("info").strip()
        ):
            fence = None
        lines[i] = _blank(line)
    masked = "\n".join(lines)
    return _CODE_SPAN.sub(lambda m: m.group("ticks") + _blank(m.group("body")) + m.group("ticks"), masked)


def _is_escaped(text: str, index: int) -> bool:
    """True if the character at `index` is preceded by an odd number of backslashes."""
    backslashes = 0
    while index - backslashes > 0 and text[index - backslashes - 1] == "\\":
        backslashes += 1
    return backslashes % 2 == 1


def _matching_bracket(text: str, start: int) -> int | None:
    """Index of the `]` matching the `[` at `start`, or None if unmatched."""
    depth = 0
    for i in range(start, len(text)):
        if _is_escaped(text, i):
            continue
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return i
    return None


def _strip_angle_brackets(dest: str) -> str:
    return dest[1:-1] if dest.startswith("<") and dest.endswith(">") else dest


def _parse_destination(text: str, start: int) -> tuple[str, int] | None:
    """
    Parse `(dest)` or `(dest "title")` beginning at the `(` at `start`.

    Returns the destination and the index just past the closing `)`.
    """
    i = start + 1
    while i < len(text) and text[i] in " \t\n":
        i += 1
    if i < len(text) and text[i] == "<":
        end = text.find(">", i)
        if end == -1:
            return None
        dest, i = text[i + 1 : end], end + 1
    else:
        begin, depth = i, 0
        while i < len(text):
            char = text[i]
            if char in " \t\n" and depth == 0:
                break
            if not _is_escaped(text, i):
                if char == "(":
                    depth += 1
                elif char == ")":
                    if depth == 0:
                        break
                    depth -= 1
            i += 1
        dest = text[begin:i]
    while i < len(text) and text[i] in " \t\n":
        i += 1
    # An optional title, which we do not care about beyond skipping it.
    if i < len(text) and text[i] in "\"'(":
        closer = ")" if text[i] == "(" else text[i]
        end = text.find(closer, i + 1)
        if end == -1:
            return None
        i = end + 1
        while i < len(text) and text[i] in " \t\n":
            i += 1
    if i >= len(text) or text[i] != ")":
        return None
    return dest, i + 1


def _normalize_label(label: str) -> str:
    return " ".join(label.split()).lower()


def _definitions(text: str) -> tuple[dict[str, str], str]:
    """Collect reference-link definitions, and blank the lines that hold them."""
    found = {}
    for match in _DEFINITION.finditer(text):
        found[_normalize_label(match.group("label"))] = _strip_angle_brackets(match.group("dest"))
    spans = [m.span() for m in _DEFINITION.finditer(text)] + [m.span() for m in _FOOTNOTE_DEFINITION.finditer(text)]
    prose = text
    for start, end in spans:
        prose = prose[:start] + _blank(prose[start:end]) + prose[end:]
    return found, prose


def _wikilink_target(inner: str) -> str:
    """The page part of a wikilink body: `page|alias` and `page#section` both name `page`."""
    return inner.split("|")[0].split("#")[0].strip()


def _markdown_links(text: str, definitions: dict[str, str]) -> Iterator[tuple[int, str, LinkKind]]:
    """Walk the text yielding (offset, target, kind) for every bracketed link form."""
    i, n = 0, len(text)
    while i < n:
        if text[i] != "[" or _is_escaped(text, i):
            i += 1
            continue
        is_image = i > 0 and text[i - 1] == "!" and not _is_escaped(text, i - 1)

        if text.startswith("[[", i):
            end = text.find("]]", i + 2)
            if end == -1:
                i += 1
                continue
            target = _wikilink_target(text[i + 2 : end])
            if target:
                yield i, target, LinkKind.IMAGE if is_image else LinkKind.WIKILINK
            i = end + 2
            continue

        close = _matching_bracket(text, i)
        if close is None:
            i += 1
            continue
        label = text[i + 1 : close]

        if close + 1 < n and text[close + 1] == "(":
            parsed = _parse_destination(text, close + 1)
            if parsed is not None:
                dest, end = parsed
                if dest:
                    yield i, _strip_angle_brackets(dest), LinkKind.IMAGE if is_image else LinkKind.INLINE
                i = end
                continue

        if close + 1 < n and text[close + 1] == "[":
            label_end = _matching_bracket(text, close + 1)
            if label_end is not None:
                reference = text[close + 2 : label_end] or label
                referenced = definitions.get(_normalize_label(reference))
                if referenced:
                    yield i, referenced, LinkKind.IMAGE if is_image else LinkKind.REFERENCE
                i = label_end + 1
                continue

        shortcut = definitions.get(_normalize_label(label))
        if shortcut:
            yield i, shortcut, LinkKind.IMAGE if is_image else LinkKind.REFERENCE
        i = close + 1


def _html_links(text: str) -> Iterator[tuple[int, str, LinkKind]]:
    """`href` and `src` attributes on any raw HTML tag."""
    for tag in _HTML_TAG.finditer(text):
        for attribute in _HTML_ATTRIBUTE.finditer(tag.group()):
            value = attribute.group(1).strip("\"'")
            if value:
                yield tag.start() + attribute.start(1), value, LinkKind.HTML


def _citations(text: str) -> Iterator[tuple[int, str, LinkKind]]:
    """
    Bare repo-relative paths used as provenance.

    Gatherings list their sources in frontmatter and distillations cite claims
    inline as `(<date>, <path>)`. These are the references that matter most —
    they are the evidence a derived artefact rests on — and until recently they
    were the ones nothing checked.
    """
    frontmatter = _FRONTMATTER.match(text)
    if frontmatter:
        for match in _YAML_PATH.finditer(frontmatter.group("body")):
            yield frontmatter.start("body") + match.start("path"), match.group("path"), LinkKind.CITATION
    for match in _DATED_CITATION.finditer(text):
        yield match.start("path"), match.group("path"), LinkKind.CITATION


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
    masked = _mask_code(text)
    definitions, prose = _definitions(masked)
    line_starts = [0] + [i + 1 for i, char in enumerate(text) if char == "\n"]

    def line_of(offset: int) -> int:
        low, high = 0, len(line_starts) - 1
        while low < high:
            mid = (low + high + 1) // 2
            if line_starts[mid] <= offset:
                low = mid
            else:
                high = mid - 1
        return low + 1

    found = list(_markdown_links(prose, definitions)) + list(_html_links(prose)) + list(_citations(masked))
    links: dict[tuple[int, str], Link] = {}
    for offset, target, kind in sorted(found, key=lambda item: item[0]):
        target = target.strip()
        if not _is_repo_reference(target):
            continue
        line = line_of(offset)
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
        lines = [f"{source}: {len(items)} link{'s' if len(items) > 1 else ''} that go nowhere"]
        for item in sorted(items, key=lambda i: i.link.line):
            suggestion = f" — moved to {item.suggestion}?" if item.suggestion else ""
            lines.append(f"  line {item.link.line}: {item.link.target} ({item.reason}){suggestion}")
        summaries.append("\n".join(lines))
    return summaries


def check_links(root: Path, *, skip: Collection[str] = SKIPPED_ROOTS) -> list[BrokenLink]:
    """
    Every reference in the repository's own markdown that no longer lands anywhere.

    Where a file with the target's name exists somewhere else — which is what a
    rename looks like from here — the new location is offered as a suggestion.
    """
    corpus = _Corpus.scan(root)
    skipped = tuple(skip)
    broken = []
    for path in sorted(_walk(root)):
        if path.suffix != ".md" or path.parts[0] in skipped:
            continue
        for link in extract_links((root / path).read_text(errors="replace"), source=path):
            found, reason = resolve(link, corpus)
            if found is None:
                name = Path(unquote(link.target.split("#")[0])).name
                broken.append(BrokenLink(link=link, reason=reason, suggestion=corpus.unique(name)))
    return broken
