"""Tests for the repository as a graph: nodes by path, their labels and edges from both bodies."""

from pathlib import Path

from commonplace._graph import Graph, Node, links
from commonplace._marginalia import marginalia_path

NOTE = Path("notes/ideas.md")
OTHER = Path("notes/other.md")


def _write(root: Path, files: dict[Path, str]) -> list[Path]:
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    return [path for path in files if not path.parts[0].startswith(".")]


def test_a_nodes_labels_are_its_own_tags_then_its_marginalias(tmp_path):
    _write(
        tmp_path,
        {
            NOTE: "---\ntags:\n- tea\n---\n# Ideas\n",
            marginalia_path(NOTE): "---\nmarginalia: 1\ntags:\n- hidden\n- tea\n---\n",
        },
    )

    assert Node(tmp_path, NOTE).labels == ["tea", "hidden"]


def test_an_edge_in_marginalia_is_written_in_their_file_and_lands_from_the_note(tmp_path):
    """The second body is a file of its own, so that's where the edge is; the edge is the note's, so it lands from it."""
    files = _write(
        tmp_path,
        {
            NOTE: "# Ideas\n",
            OTHER: "# Other\n",
            marginalia_path(NOTE): "---\nmarginalia: 1\n---\n\n- see [the other](other.md)\n",
        },
    )

    [edge] = Node(tmp_path, NOTE).edges

    assert (edge.link.source, edge.link.line) == (marginalia_path(NOTE), 5)
    assert Graph(tmp_path, files).lands(edge) == [OTHER]


def test_a_note_labelled_hidden_in_its_own_frontmatter_is_left_out_of_links(tmp_path):
    files = _write(tmp_path, {NOTE: "See [[other]].\n", OTHER: "---\ntags: [hidden]\n---\n# Other\n"})
    graph = Graph(tmp_path, files)

    assert links(graph, NOTE) == []
    assert [neighbour.other for neighbour in links(graph, NOTE, include_hidden=True)] == ["/notes/other"]
