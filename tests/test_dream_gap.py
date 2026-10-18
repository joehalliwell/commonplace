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


def test_gap_check_marks_each_image_used_unused_or_leaked(scratch: Path):
    gap("pool", str(scratch))
    (scratch / "scenes.txt").write_text(
        "Title: T\nSummary: s\n\nTelling.\n\nUnused:\nGreenhouse glass frames a calendar.\n"
    )
    assert gap("check", str(scratch)).splitlines() == [
        (
            "- [[/journal/a]], Morning: A grant form pinned to a greenhouse door. (used);"
            " A woman called Priya waters the filing cabinet. (leaked)"
        ),
        (
            "- [[/memory/claude/b]]: A painted floor line slides under a door. (used);"
            " Greenhouse glass frames a calendar. (unused)"
        ),
    ]


def test_gap_check_reports_unused_line_not_in_pool(scratch: Path):
    gap("pool", str(scratch))
    (scratch / "scenes.txt").write_text("Title: T\n\nTelling.\n\nUnused:\nA greenhouse door.\n")
    assert gap("check", str(scratch)).splitlines()[-2:] == ["Unused but not in the pool:", "- A greenhouse door."]
