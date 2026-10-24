import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "plugins/commonplace-skills/skills/dream/scripts/gap.py"


def gap(*args: str) -> str:
    """Run the script as the skill does, returning what it prints."""
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    """A scratch dir as residue and two imagery subagents leave it."""
    fragments = [
        {"path": "journal/a.md", "heading": "Morning", "draw": "recent"},
        {"path": "memory/claude/b.md", "heading": None, "draw": "deep"},
    ]
    (tmp_path / "fragments.json").write_text(json.dumps(fragments))
    for n, text in {1: "Met Priya at Kew about the grant.", 2: "The deadline slipped again."}.items():
        (tmp_path / "passages").mkdir(exist_ok=True)
        (tmp_path / "passages" / f"{n}.txt").write_text(text)
    images = {
        1: "A grant form pinned to a greenhouse door.\nA woman called Priya waters the filing cabinet.\n",
        2: "A painted floor line slides under a door.\nGreenhouse glass frames a calendar.\n",
    }
    for n, text in images.items():
        (tmp_path / "images").mkdir(exist_ok=True)
        (tmp_path / "images" / f"{n}.txt").write_text(text)
    return tmp_path


def test_gap_pool_drops_image_reusing_passage_name_as_leaked(scratch: Path):
    gap("pool", str(scratch))
    pool = (scratch / "pool.txt").read_text().splitlines()
    assert "A woman called Priya waters the filing cabinet." not in pool
    assert sorted(pool) == sorted(
        [
            "A grant form pinned to a greenhouse door.",
            "A painted floor line slides under a door.",
            "Greenhouse glass frames a calendar.",
        ]
    )


def test_gap_pool_prints_counts_not_images(scratch: Path):
    printed = gap("pool", str(scratch))
    assert "greenhouse" not in printed.lower()
    assert "3" in printed and "1" in printed


def test_gap_pool_different_seeds_shuffle_differently(scratch: Path):
    orders = set()
    for seed in range(10):
        gap("pool", str(scratch), "--seed", str(seed))
        orders.add((scratch / "pool.txt").read_text())
    assert len(orders) > 1


SCENES = "Title: The Door\nSummary: grant-door\n\nI watered the form.\n\nUnused:\nGreenhouse glass frames a calendar.\n"


@pytest.fixture
def dreamt(scratch: Path) -> Path:
    """A scratch dir after every phase: pooled, condensed, split, revised and interpreted."""
    gap("pool", str(scratch))
    (scratch / "scenes.txt").write_text(SCENES)
    gap("split", str(scratch))
    (scratch / "dream.txt").write_text("Title: The Green Door\n\nI watered the form, once.\n")
    (scratch / "accents.txt").write_text("The grant, from 1.txt, because it was due.\n")
    (scratch / "interpretation.txt").write_text("The form is the grant [[/journal/a]], and the door [[/notes/x]].\n")
    return scratch


def record(scratch: Path, root: Path) -> tuple[str, str]:
    """Write the record as the skill does, returning what the script printed and what it wrote."""
    printed = gap(
        "record", str(scratch), "--root", str(root), "--agent", "claude-code",
        "--date", "2026-10-24", "--by", "dream/0.26.0", "--at", "2026-10-24T12:00:00Z",
    )  # fmt: skip
    return printed, (root / printed.strip()).read_text()


def test_gap_split_separates_telling_from_unused_list(scratch: Path):
    gap("pool", str(scratch))
    (scratch / "scenes.txt").write_text(SCENES)
    gap("split", str(scratch))
    assert (scratch / "telling.txt").read_text() == "Title: The Door\nSummary: grant-door\n\nI watered the form.\n"
    assert (scratch / "unused.txt").read_text() == "Greenhouse glass frames a calendar.\n"


def test_gap_split_prints_nothing(scratch: Path):
    (scratch / "scenes.txt").write_text(SCENES)
    assert gap("split", str(scratch)) == ""


def test_gap_split_without_unused_section_fails(scratch: Path):
    (scratch / "scenes.txt").write_text("Title: T\nSummary: s\n\nTelling.\n")
    run = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "split", str(scratch)], capture_output=True, text=True, check=False
    )
    assert run.returncode != 0
    assert "Telling" not in run.stderr + run.stdout


def test_gap_record_prints_only_its_path_named_from_the_slug(dreamt: Path, tmp_path: Path):
    printed, _ = record(dreamt, tmp_path)
    assert printed == ".commonplace/skills/dream/claude-code/2026/10/2026-10-24-grant-door.md\n"


def test_gap_record_marks_each_image_used_unused_or_leaked(dreamt: Path, tmp_path: Path):
    _, text = record(dreamt, tmp_path)
    assert (
        "- [[/journal/a]], Morning: A grant form pinned to a greenhouse door. (used);"
        " A woman called Priya waters the filing cabinet. (leaked)\n"
        "- [[/memory/claude/b]]: A painted floor line slides under a door. (used);"
        " Greenhouse glass frames a calendar. (unused)\n"
    ) in text


def test_gap_record_keeps_frontmatter_unpolished_telling_and_accents(dreamt: Path, tmp_path: Path):
    _, text = record(dreamt, tmp_path)
    assert text.startswith(
        "---\ntitle: The Green Door\nresidue:\n  - /journal/a.md\n  - /memory/claude/b.md\n"
        "journal: /agent-journal/claude-code/2026/10/2026-10-24.md\n"
        "generated: {by: dream/0.26.0, at: 2026-10-24T12:00:00Z}\n---\n\n# The Green Door\n"
    )
    assert "## Unpolished\nI watered the form.\n" in text
    assert "## Accents\nThe grant, from 1.txt, because it was due.\n" in text


def test_gap_record_reports_unused_line_not_in_pool(dreamt: Path, tmp_path: Path):
    (dreamt / "unused.txt").write_text("A greenhouse door.\n")
    _, text = record(dreamt, tmp_path)
    assert "Unused but not in the pool:\n- A greenhouse door.\n" in text


def test_gap_record_scores_interpretation_citations_against_residue(dreamt: Path, tmp_path: Path):
    _, text = record(dreamt, tmp_path)
    assert "## Interpretation\n1 of 2 cited sources were residue; 1 of 2 fragments found.\n" in text
