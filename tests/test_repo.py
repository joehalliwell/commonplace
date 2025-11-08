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


def test_has_remote_exists(test_repo):
    """Test has_remote returns True when remote exists."""
    test_repo.git.remotes.create("origin", "https://github.com/test/repo.git")
    assert test_repo.has_remote("origin")


def test_has_remote_not_exists(test_repo):
    """Test has_remote returns False when remote doesn't exist."""
    assert not test_repo.has_remote("origin")


def test_has_remote_custom_name(test_repo):
    """Test has_remote works with custom remote names."""
    test_repo.git.remotes.create("upstream", "https://github.com/test/repo.git")
    assert test_repo.has_remote("upstream")
    assert not test_repo.has_remote("origin")


def test_commit_auto_indexes_by_default(test_repo, monkeypatch):
    """Test that commit auto-indexes when config.auto_index is True."""
    # Track if index was called
    index_called = []

    def mock_index(repo, rebuild):
        index_called.append((repo, rebuild))

    # Patch the index function
    import commonplace._search._commands

    monkeypatch.setattr(commonplace._search._commands, "index", mock_index)

    # Ensure config has auto_index=True (default)
    assert test_repo.config.auto_index is True

    # Create and commit a note
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Test commit")

    # Verify index was called once with rebuild=False
    assert len(index_called) == 1
    assert index_called[0] == (test_repo, False)


def test_commit_no_index_flag_disables_indexing(test_repo, monkeypatch):
    """Test that commit with auto_index=False doesn't index."""
    # Track if index was called
    index_called = []

    def mock_index(repo, rebuild):
        index_called.append((repo, rebuild))

    # Patch the index function
    import commonplace._search._commands

    monkeypatch.setattr(commonplace._search._commands, "index", mock_index)

    # Create and commit a note with auto_index=False
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Test commit", auto_index=False)

    # Verify index was NOT called
    assert len(index_called) == 0


def test_commit_index_flag_overrides_config(test_repo, monkeypatch):
    """Test that auto_index=True overrides config when auto_index is False."""
    # Track if index was called
    index_called = []

    def mock_index(repo, rebuild):
        index_called.append((repo, rebuild))

    # Patch the index function
    import commonplace._search._commands

    monkeypatch.setattr(commonplace._search._commands, "index", mock_index)

    # Set config to auto_index=False
    monkeypatch.setattr(test_repo.config, "auto_index", False)

    # Create and commit a note with auto_index=True (override)
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Test commit", auto_index=True)

    # Verify index WAS called (flag overrode config)
    assert len(index_called) == 1
    assert index_called[0] == (test_repo, False)


def test_commit_no_changes_skips_indexing(test_repo, monkeypatch):
    """Test that commit with no changes doesn't trigger indexing."""
    # Track if index was called
    index_called = []

    def mock_index(repo, rebuild):
        index_called.append((repo, rebuild))

    # Patch the index function
    import commonplace._search._commands

    monkeypatch.setattr(commonplace._search._commands, "index", mock_index)

    # Create initial commit
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Initial commit")

    # Clear the tracking
    index_called.clear()

    # Try to commit with no changes
    test_repo.commit("No changes")

    # Verify index was NOT called (no changes means no commit means no index)
    assert len(index_called) == 0
