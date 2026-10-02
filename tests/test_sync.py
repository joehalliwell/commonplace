"""Tests for sync functionality."""

from pathlib import Path

import pytest
from pygit2 import init_repository

from commonplace._repo import Commonplace
from commonplace._types import Note, RepoPath


@pytest.fixture
def remote_repo(tmp_path):
    """Create a bare remote repository for testing."""
    remote_path = tmp_path / "remote.git"
    init_repository(remote_path, bare=True)
    return remote_path


@pytest.fixture
def local_repo_with_remote(tmp_path, remote_repo):
    """Create a local repository with a remote configured."""
    local_path = tmp_path / "local"
    Commonplace.init(local_path)
    repo = Commonplace.open(local_path)

    # Configure remote
    repo.git.remotes.create("origin", remote_repo.as_posix())

    # Create initial commit
    note = Note(
        repo_path=RepoPath(path=Path("initial.md"), ref=""),
        body="# Initial\nFirst note",
    )
    repo.save(note)
    repo.commit("Initial commit")

    yield repo
    repo.close()


def _pushed(repo, remote: str = "origin") -> bool:
    """Whether the remote's main is at the local HEAD."""
    return repo.git.lookup_reference(f"refs/remotes/{remote}/main").target == repo.git.head.target


def test_sync_no_remote_fails(test_repo):
    """Test that sync fails when remote doesn't exist."""
    with pytest.raises(ValueError, match="Remote 'origin' not found"):
        test_repo.sync()


def test_sync_initial_commit_only_is_pushed(tmp_path, remote_repo):
    """Test that sync works even when only the initial commit exists."""
    local_path = tmp_path / "local"
    Commonplace.init(local_path)  # Creates initial commit with .gitignore
    repo = Commonplace.open(local_path)
    repo.git.remotes.create("origin", remote_repo.as_posix())

    repo.sync()

    assert _pushed(repo)
    repo.close()


def test_sync_adds_untracked_files(local_repo_with_remote):
    """Test that sync adds untracked files."""
    (local_repo_with_remote.root / "untracked.md").write_text("# Untracked")

    local_repo_with_remote.sync()

    assert "untracked.md" in local_repo_with_remote.git.head.peel().tree
    assert _pushed(local_repo_with_remote)


def test_sync_auto_commits_changes(local_repo_with_remote):
    """Test that sync auto-commits uncommitted changes."""
    (local_repo_with_remote.root / "initial.md").write_text("# Modified")

    local_repo_with_remote.sync(auto_commit=True)

    assert local_repo_with_remote.git.head.peel().tree["initial.md"].data == b"# Modified"
    assert _pushed(local_repo_with_remote)


def test_sync_refuses_uncommitted_without_auto_commit(local_repo_with_remote):
    """Test that sync fails without auto_commit when there are uncommitted changes."""
    # Modify a file
    (local_repo_with_remote.root / "initial.md").write_text("# Modified")

    # Git itself will refuse to pull with uncommitted changes
    with pytest.raises(ValueError, match="cannot pull with rebase"):
        local_repo_with_remote.sync(auto_commit=False)


def test_sync_first_push(local_repo_with_remote):
    """Test sync on first push to empty remote."""
    local_repo_with_remote.sync()

    assert _pushed(local_repo_with_remote)


def test_sync_fast_forward(tmp_path, remote_repo):
    """Test sync with fast-forward merge."""
    # Create first local repo and push
    local1_path = tmp_path / "local1"
    Commonplace.init(local1_path)
    repo1 = Commonplace.open(local1_path)
    repo1.git.remotes.create("origin", remote_repo.as_posix())

    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        body="# Test",
    )
    repo1.save(note)
    repo1.commit("Initial commit")
    repo1.sync()
    commit1_id = repo1.git.head.target
    repo1.close()

    # Create second local repo (clone)
    local2_path = tmp_path / "local2"
    Commonplace.init(local2_path)
    repo2 = Commonplace.open(local2_path)
    repo2.git.remotes.create("origin", remote_repo.as_posix())

    # Fetch and set up tracking
    remote = repo2.git.remotes["origin"]
    remote.fetch()

    # Set HEAD to remote/main (force=True because main already exists from init())
    remote_ref = repo2.git.lookup_reference("refs/remotes/origin/main")
    repo2.git.create_reference("refs/heads/main", remote_ref.target, force=True)
    repo2.git.checkout("refs/heads/main")

    # Make a change in repo1 and push
    note2 = Note(
        repo_path=RepoPath(path=Path("test2.md"), ref=""),
        body="# Test 2",
    )
    repo1 = Commonplace.open(local1_path)
    repo1.save(note2)
    repo1.commit("Second commit")
    repo1.sync()
    commit2_id = repo1.git.head.target
    repo1.close()

    # Now sync repo2 - should fast-forward
    repo2.sync()

    # Verify repo2 is at commit2
    assert repo2.git.head.target == commit2_id
    assert repo2.git.head.target != commit1_id

    repo2.close()


def test_sync_already_up_to_date(local_repo_with_remote):
    """Test sync when already up to date."""
    local_repo_with_remote.sync()
    head = local_repo_with_remote.git.head.target

    local_repo_with_remote.sync()

    assert local_repo_with_remote.git.head.target == head
    assert _pushed(local_repo_with_remote)


def test_sync_with_custom_remote_name(tmp_path):
    """Test sync with custom remote name."""
    remote_path = tmp_path / "upstream.git"
    init_repository(remote_path, bare=True)

    local_path = tmp_path / "local"
    Commonplace.init(local_path)
    repo = Commonplace.open(local_path)
    repo.git.remotes.create("upstream", remote_path.as_posix())

    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        body="# Test",
    )
    repo.save(note)
    repo.commit("Initial commit")

    # Sync with custom remote
    repo.sync(remote_name="upstream")

    assert _pushed(repo, "upstream")

    repo.close()


def test_sync_merge_strategy(tmp_path, remote_repo):
    """Test sync with merge strategy instead of rebase."""
    # Create and push initial commit
    local_path = tmp_path / "local"
    Commonplace.init(local_path)
    repo = Commonplace.open(local_path)
    repo.git.remotes.create("origin", remote_repo.as_posix())

    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        body="# Test",
    )
    repo.save(note)
    repo.commit("Initial commit")
    repo.sync(strategy="merge")

    assert _pushed(repo)
    repo.close()
