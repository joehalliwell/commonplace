from pathlib import Path

from commonplace._types import RepoPath


def test_repo_path_without_ref_is_uncommitted_and_prints_bare():
    repo_path = RepoPath(Path("notes/idea.md"))

    assert repo_path.ref is None
    assert str(repo_path) == "notes/idea.md"
