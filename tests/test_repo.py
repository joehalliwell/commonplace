"""Tests for repository commit functionality."""

from pathlib import Path

from commonplace._types import Note, RepoPath


def test_commit_initial_changes(test_repo):
    """Test committing the first change to a new repository."""
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Initial commit")

    assert not test_repo.git.head_is_unborn
    assert test_repo.git.head.peel().message == "Initial commit"


def test_commit_no_changes(test_repo):
    """Test that committing with no changes does nothing."""
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Initial commit")

    first_commit_id = test_repo.git.head.target
    test_repo.commit("Should not create commit")

    assert test_repo.git.head.target == first_commit_id


def test_commit_subsequent_changes(test_repo):
    """Test committing changes after initial commit."""
    note1 = Note(
        repo_path=RepoPath(path=Path("test1.md"), ref=""),
        content="# Test 1\nFirst note",
    )
    test_repo.save(note1)
    test_repo.commit("Initial commit")
    first_commit_id = test_repo.git.head.target

    note2 = Note(
        repo_path=RepoPath(path=Path("test2.md"), ref=""),
        content="# Test 2\nSecond note",
    )
    test_repo.save(note2)
    test_repo.commit("Add second note")

    assert test_repo.git.head.target != first_commit_id
    assert test_repo.git.head.peel().message == "Add second note"


def test_commit_modified_file(test_repo):
    """Test committing modifications to an existing file."""
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nOriginal content",
    )
    test_repo.save(note)
    test_repo.commit("Initial commit")
    first_commit_id = test_repo.git.head.target

    modified_note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nModified content",
    )
    test_repo.save(modified_note)
    test_repo.commit("Update note")

    assert test_repo.git.head.target != first_commit_id
    assert test_repo.git.head.peel().message == "Update note"


def test_index_matches_head_after_commit(test_repo):
    """Test that index tree matches HEAD tree after commit (not previous HEAD)."""
    from pygit2.enums import ObjectType

    # First commit
    note1 = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nOriginal content",
    )
    test_repo.save(note1)
    test_repo.commit("Initial commit")

    # Second commit modifies the file
    note2 = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nModified content",
    )
    test_repo.save(note2)
    test_repo.commit("Update note")

    # Reload index from disk (simulates what happens in a new command/process)
    test_repo.git.index.read()

    # After commit, the index tree should match the HEAD tree
    # If they don't match, git will show staged changes (looks like a revert)
    index_tree_id = test_repo.git.index.write_tree()
    head_commit = test_repo.git.head.peel(ObjectType.COMMIT)
    head_tree_id = head_commit.tree.id

    assert index_tree_id == head_tree_id, (
        f"Index tree {index_tree_id} doesn't match HEAD tree {head_tree_id}. "
        "This makes it look like there are staged changes (a revert)!"
    )
