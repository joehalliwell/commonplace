import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "plugins/commonplace-skills/skills/dream/scripts/residue.py"
OLD = "2020-01-01T00:00:00Z"


def commit(root: Path, files: dict[str, str], date: str | None = None) -> None:
    """Write and commit files, backdated to `date` if given."""
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    env = os.environ | ({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {})
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "files"], check=True, env=env)


def run(root: Path, out: Path, seed: int = 0) -> str:
    """Run the script as the skill does, returning what it prints."""
    args = [sys.executable, "-I", str(SCRIPT), "--root", str(root), "--out", str(out), "--seed", str(seed)]
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def residue(root: Path, seed: int = 0) -> list[dict]:
    """The fragments a run writes, each with the text of its passage file."""
    out = Path(tempfile.mkdtemp())
    run(root, out, seed)
    fragments = json.loads((out / "fragments.json").read_text())
    return [f | {"text": (out / "passages" / f"{n}.txt").read_text()} for n, f in enumerate(fragments, 1)]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "T"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "commit.gpgsign", "false"], check=True)
    return tmp_path


def test_residue_file_without_headings_strips_frontmatter(repo: Path):
    commit(
        repo, {"memory/claude/profile.md": "---\nupdated_at: '2026-10-17'\nsource_export: blob\n---\n\nLikes kites.\n"}
    )
    [fragment] = residue(repo)
    assert fragment["path"] == "memory/claude/profile.md"
    assert fragment["heading"] is None
    assert fragment["text"].strip() == "Likes kites."


def test_residue_file_with_headings_takes_one_section_cut_to_limit(repo: Path):
    commit(repo, {"chats/a.md": "---\ntitle: t\n---\n# T\n\n## User\n\n" + "x" * 3000 + "\n"})
    [fragment] = residue(repo)
    assert fragment["heading"] == "User"
    assert fragment["text"] == "x" * 2000


def test_residue_section_stops_at_next_heading_without_heading_line(repo: Path):
    commit(repo, {"chats/a.md": "## User [created:: 2026-10-14]\n\nask\n\n## Claude\n\nanswer\n"})
    fragments = [residue(repo, seed)[0] for seed in range(20)]
    assert {f["heading"]: f["text"].split() for f in fragments} == {
        "User [created:: 2026-10-14]": ["ask"],
        "Claude": ["answer"],
    }


def test_residue_recent_memory_capped_at_two(repo: Path):
    commit(repo, {f"journal/old{i}.md": f"old {i}\n" for i in range(20)}, date=OLD)
    commit(repo, {f"memory/claude/m{i}.md": f"memory {i}\n" for i in range(10)} | {"journal/new.md": "new\n"})
    for seed in range(20):
        recent = [f for f in residue(repo, seed) if f["draw"] == "recent"]
        assert len(recent) == 3
        assert sum(f["path"].startswith("memory/") for f in recent) == 2


def test_residue_few_recent_tops_up_from_deep(repo: Path):
    commit(repo, {f"journal/old{i}.md": f"old {i}\n" for i in range(20)}, date=OLD)
    commit(repo, {"journal/new.md": "new\n"})
    fragments = residue(repo)
    assert [f["draw"] for f in fragments].count("recent") == 1
    assert len(fragments) == 12
    assert len({f["path"] for f in fragments}) == 12


def test_residue_excludes_tasks_and_non_markdown(repo: Path):
    commit(
        repo, {"chats/claude-tasks/t.md": "task\n", "notes/pic.jpg": "jpg", "src/x.md": "code\n", "notes/n.md": "n\n"}
    )
    assert [f["path"] for f in residue(repo)] == ["notes/n.md"]


def test_residue_same_seed_same_sample(repo: Path):
    commit(repo, {f"journal/{i}.md": f"## A\n\n{i}a\n\n## B\n\n{i}b\n" for i in range(30)})
    assert residue(repo, seed=7) == residue(repo, seed=7)
    assert residue(repo, seed=7) != residue(repo, seed=8)


def test_residue_prints_no_fragment_text(repo: Path, tmp_path: Path):
    commit(repo, {"journal/a.md": "## Morning\n\nThe kettle sang.\n"})
    printed = run(repo, tmp_path / "out")
    assert "kettle" not in printed
    assert "journal" not in printed
