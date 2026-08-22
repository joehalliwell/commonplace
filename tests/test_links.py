"""Tests for link extraction and broken-link checking."""

from pathlib import Path

import pytest

from commonplace._links import LinkKind, check_links, extract_links

SOURCE = Path("notes/note.md")


def targets(text: str, source: Path = SOURCE) -> list[str]:
    """The raw targets extracted from `text`, in order."""
    return [link.target for link in extract_links(text, source=source)]


# --- Inline links and images ------------------------------------------------


def test_extract_inline_link_yields_destination():
    assert targets("See [the note](other.md) for more.") == ["other.md"]


def test_extract_inline_link_with_title_ignores_title():
    assert targets('[text](other.md "A title")') == ["other.md"]
    assert targets("[text](other.md 'A title')") == ["other.md"]


def test_extract_inline_link_with_angle_brackets_strips_them():
    assert targets("[text](<a note with spaces.md>)") == ["a note with spaces.md"]


def test_extract_inline_link_with_nested_parens_keeps_whole_destination():
    assert targets("[text](notes/foo_(draft).md)") == ["notes/foo_(draft).md"]


def test_extract_inline_link_with_nested_brackets_in_text_yields_destination():
    assert targets("[see [this] thing](other.md)") == ["other.md"]


def test_extract_image_is_marked_as_image():
    links = extract_links("![alt](picture.png)", source=SOURCE)
    assert [link.target for link in links] == ["picture.png"]
    assert links[0].kind is LinkKind.IMAGE


def test_extract_empty_destination_is_ignored():
    assert targets("[text]()") == []


def test_extract_escaped_bracket_is_not_a_link():
    assert targets(r"\[not a link](other.md)") == []


# --- Reference links --------------------------------------------------------


def test_extract_reference_link_resolves_via_definition():
    text = "See [the note][ref].\n\n[ref]: other.md\n"
    assert targets(text) == ["other.md"]


def test_extract_collapsed_reference_link_uses_text_as_label():
    text = "See [other][].\n\n[other]: other.md\n"
    assert targets(text) == ["other.md"]


def test_extract_shortcut_reference_link_resolves_via_definition():
    text = "See [other].\n\n[other]: other.md\n"
    assert targets(text) == ["other.md"]


def test_extract_bracketed_text_without_definition_is_not_a_link():
    assert targets("An aside [in brackets] here.") == []


def test_extract_reference_definition_with_angle_brackets_strips_them():
    text = "See [the note][ref].\n\n[ref]: <a note.md>\n"
    assert targets(text) == ["a note.md"]


def test_extract_reference_label_matching_is_case_insensitive():
    text = "See [the note][Ref].\n\n[ref]: other.md\n"
    assert targets(text) == ["other.md"]


# --- Wikilinks --------------------------------------------------------------


def test_extract_wikilink_yields_page_name():
    links = extract_links("See [[other note]] for more.", source=SOURCE)
    assert [link.target for link in links] == ["other note"]
    assert links[0].kind is LinkKind.WIKILINK


def test_extract_wikilink_with_alias_yields_page_name():
    assert targets("See [[other note|that thing]].") == ["other note"]


def test_extract_wikilink_with_heading_yields_page_name():
    assert targets("See [[other note#Section]].") == ["other note"]


def test_extract_wikilink_embed_yields_page_name():
    assert targets("![[picture.png]]") == ["picture.png"]


# --- HTML -------------------------------------------------------------------


def test_extract_html_anchor_href_yields_destination():
    assert targets('<a href="other.md">text</a>') == ["other.md"]


def test_extract_html_image_src_yields_destination():
    assert targets("<img src='picture.png' alt='x'>") == ["picture.png"]


# --- Things that are not repository references ------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "[text](https://example.com)",
        "[text](http://example.com)",
        "[text](mailto:joe@example.com)",
        "[text](ftp://example.com/x)",
        "[text](data:image/png;base64,AAAA)",
        "[text](//example.com/x)",
        "<https://example.com>",
    ],
)
def test_extract_external_target_is_not_a_repository_reference(text):
    assert targets(text) == []


def test_extract_fragment_only_target_is_not_a_repository_reference():
    assert targets("[text](#a-heading)") == []


def test_extract_footnote_reference_is_not_a_link():
    assert targets("Some claim.[^1]\n\n[^1]: A footnote.\n") == []


# --- Code is not prose ------------------------------------------------------


def test_extract_ignores_links_inside_fenced_code_block():
    text = "```\n[text](other.md)\n```\n"
    assert targets(text) == []


def test_extract_ignores_links_inside_tilde_fenced_code_block():
    text = "~~~markdown\n[text](other.md)\n~~~\n"
    assert targets(text) == []


def test_extract_ignores_links_inside_inline_code_span():
    assert targets("Write it as `[text](other.md)` in markdown.") == []


def test_extract_finds_links_after_a_closed_fence():
    text = "```\n[a](in-code.md)\n```\n\n[b](real.md)\n"
    assert targets(text) == ["real.md"]


# --- Provenance citations ---------------------------------------------------


def test_extract_frontmatter_sources_are_citations():
    text = "---\nkind: gathering\nsources:\n  - chats/claude/2026/01/2026-01-01-a.md\n---\n\n# Gathering\n"
    links = extract_links(text, source=Path("topics/x/gathering.md"))
    assert [link.target for link in links] == ["chats/claude/2026/01/2026-01-01-a.md"]
    assert links[0].kind is LinkKind.CITATION


def test_extract_frontmatter_source_gathering_is_a_citation():
    text = "---\nkind: distillation\nsource_gathering: topics/x/gathering.md\n---\n"
    assert targets(text, Path("topics/x/distillation.md")) == ["topics/x/gathering.md"]


def test_extract_inline_dated_citation_is_a_citation():
    text = "Joe worried about drift (2026-01-01, chats/claude/2026/01/2026-01-01-a.md)."
    links = extract_links(text, source=Path("topics/x/distillation.md"))
    assert [link.target for link in links] == ["chats/claude/2026/01/2026-01-01-a.md"]
    assert links[0].kind is LinkKind.CITATION


def test_extract_frontmatter_non_path_values_are_not_citations():
    text = '---\nkind: gathering\nqueries:\n  - "art"\nupdated: 2026-02-17\n---\n'
    assert targets(text, Path("topics/x/gathering.md")) == []


# --- Line numbers -----------------------------------------------------------


def test_extract_records_one_based_line_numbers():
    text = "# Title\n\nA [first](a.md) link.\n\nA [second](b.md) link.\n"
    assert [(link.target, link.line) for link in extract_links(text, source=SOURCE)] == [("a.md", 3), ("b.md", 5)]


# --- Resolution and checking ------------------------------------------------


def write(root: Path, path: str, content: str = "") -> Path:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target


def test_check_links_relative_target_resolves_against_containing_file(tmp_path):
    write(tmp_path, "notes/other.md")
    write(tmp_path, "notes/note.md", "[text](other.md)")
    assert check_links(tmp_path) == []


def test_check_links_parent_relative_target_resolves(tmp_path):
    write(tmp_path, "notes/target.md")
    write(tmp_path, "journal/2026/entry.md", "[text](../../notes/target.md)")
    assert check_links(tmp_path) == []


def test_check_links_root_relative_target_resolves_against_repository_root(tmp_path):
    write(tmp_path, "notes/target.md")
    write(tmp_path, "journal/entry.md", "[text](/notes/target.md)")
    assert check_links(tmp_path) == []


def test_check_links_percent_encoded_target_resolves(tmp_path):
    write(tmp_path, "journal/💋.png")
    write(tmp_path, "journal/entry.md", "![💋](%F0%9F%92%8B.png)")
    assert check_links(tmp_path) == []


def test_check_links_fragment_is_stripped_before_resolving(tmp_path):
    write(tmp_path, "notes/other.md")
    write(tmp_path, "notes/note.md", "[text](other.md#a-section)")
    assert check_links(tmp_path) == []


def test_check_links_directory_target_resolves(tmp_path):
    write(tmp_path, "notes/ideas/one.md")
    write(tmp_path, "notes/note.md", "[text](ideas/)")
    assert check_links(tmp_path) == []


def test_check_links_missing_target_is_reported(tmp_path):
    write(tmp_path, "notes/note.md", "[text](gone.md)")
    broken = check_links(tmp_path)
    assert [(b.link.source, b.link.target) for b in broken] == [(Path("notes/note.md"), "gone.md")]


def test_check_links_target_outside_repository_is_reported(tmp_path):
    write(tmp_path, "notes/note.md", "[text](../../outside.md)")
    broken = check_links(tmp_path)
    assert len(broken) == 1
    assert "outside" in broken[0].reason


def test_check_links_broken_citation_is_reported(tmp_path):
    write(tmp_path, "topics/x/gathering.md", "---\nsources:\n  - chats/gemini/2024/11/a.md\n---\n")
    broken = check_links(tmp_path)
    assert [b.link.target for b in broken] == ["chats/gemini/2024/11/a.md"]


def test_check_links_wikilink_resolves_to_note_anywhere_in_repository(tmp_path):
    write(tmp_path, "notes/deep/other-note.md")
    write(tmp_path, "notes/note.md", "See [[other-note]].")
    assert check_links(tmp_path) == []


def test_check_links_skips_chat_transcripts(tmp_path):
    write(tmp_path, "chats/claude/2026/01/chat.md", "The model said [text](nonexistent.md) here.")
    assert check_links(tmp_path) == []


def test_check_links_suggests_renamed_file_with_matching_basename(tmp_path):
    write(tmp_path, "chats/gemini-takeout/2024/11/2024-11-22-a.md")
    write(tmp_path, "topics/x/gathering.md", "---\nsources:\n  - chats/gemini/2024/11/2024-11-22-a.md\n---\n")
    broken = check_links(tmp_path)
    assert len(broken) == 1
    assert broken[0].suggestion == Path("chats/gemini-takeout/2024/11/2024-11-22-a.md")


def test_check_links_ambiguous_basename_yields_no_suggestion(tmp_path):
    write(tmp_path, "notes/a/index.md")
    write(tmp_path, "notes/b/index.md")
    write(tmp_path, "notes/note.md", "[text](missing/index.md)")
    broken = check_links(tmp_path)
    assert len(broken) == 1
    assert broken[0].suggestion is None


def test_check_links_ignores_git_internals(tmp_path):
    write(tmp_path, ".git/description", "[text](gone.md)")
    write(tmp_path, ".commonplace/cache/x.md", "[text](gone.md)")
    assert check_links(tmp_path) == []
