"""Every index schema version we have ever written, against the committed examples in tests/resources/index/.

`any_index_version` is parametrised over the full range, so a bump without a matching example fails
rather than going untested. Every example holds the same chunks, which is what lets each test say the
guarantee: an index any earlier release wrote still opens to the same thing.
"""

from contextlib import closing
from pathlib import Path

from commonplace._search._sqlite import SQLiteSearchIndex
from commonplace._types import RepoPath
from tests.resources.index.make_examples import REF_A, REF_B, ExampleEmbedder

TEA = RepoPath(Path("notes/tea.md"), REF_A)
WALKS = RepoPath(Path("notes/walks.md"), REF_B)


def _open(example):
    return closing(SQLiteSearchIndex(example.path, embedder=ExampleEmbedder()))


def _found(hits) -> list[tuple[str, int]]:
    return [(str(hit.chunk.repo_path.path), hit.chunk.offset) for hit in hits]


def test_every_index_version_lists_the_same_notes(any_index_version):
    with _open(any_index_version) as index:
        assert set(index.get_indexed_paths()) == {TEA, WALKS}


def test_every_index_version_finds_by_keyword(any_index_version):
    with _open(any_index_version) as index:
        assert _found(index.search_keyword("river")) == [("notes/walks.md", 0)]


def test_every_index_version_ranks_by_its_stored_embeddings(any_index_version):
    with _open(any_index_version) as index:
        assert _found(index.search_semantic("Steep for four minutes.", limit=1)) == [("notes/tea.md", 40)]


def test_every_index_version_counts_chunks_per_note(any_index_version):
    with _open(any_index_version) as index:
        assert {stat.repo_path: stat.num_chunks for stat in index.stats()} == {TEA: 2, WALKS: 1}


def test_every_index_version_removes_a_note_from_keyword_search_too(any_index_version):
    with _open(any_index_version) as index:
        index.remove([WALKS])

        assert set(index.get_indexed_paths()) == {TEA}
        assert index.search_keyword("river") == []
