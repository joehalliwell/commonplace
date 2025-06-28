import tempfile
from pathlib import Path

import pygit2

from commonplace._git import GitRepo


def test_init_new_repo():
    """Test initializing a new git repository."""
    with tempfile.TemporaryDirectory() as temp_dir:
        git_repo = GitRepo(Path(temp_dir))

        # Should not be available initially
        assert not git_repo.is_available()

        # Initialize repo
        assert git_repo.init_repo() is True
        assert git_repo.is_available()

        # Should create .gitignore
        gitignore_path = Path(temp_dir) / ".gitignore"
        assert gitignore_path.exists()

        # Should have initial commit
        assert not git_repo.repo.head_is_unborn


def test_init_existing_repo():
    """Test initializing when repository already exists."""
    with tempfile.TemporaryDirectory() as temp_dir:
        git_repo = GitRepo(Path(temp_dir))

        # Initialize repo twice
        assert git_repo.init_repo() is True
        assert git_repo.init_repo() is True  # Should not fail


def test_commit_changes():
    """Test committing changes to repository."""
    with tempfile.TemporaryDirectory() as temp_dir:
        git_repo = GitRepo(Path(temp_dir))
        git_repo.init_repo()

        # Create a test file
        test_file = Path(temp_dir) / "test.md"
        test_file.write_text("# Test content")

        # Commit the change
        assert git_repo.commit_changes("Add test file") is True


def test_no_commit_without_repo():
    """Test that commit fails gracefully without repository."""
    with tempfile.TemporaryDirectory() as temp_dir:
        git_repo = GitRepo(Path(temp_dir))

        # Should not be able to commit without repo
        assert git_repo.commit_changes("Test commit") is False


def test_discover_existing_repo():
    """Test discovering an existing repository."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Initialize repo manually first
        git_repo1 = GitRepo(Path(temp_dir))
        git_repo1.init_repo()

        # Create new GitRepo instance - should discover existing repo
        git_repo2 = GitRepo(Path(temp_dir))
        assert git_repo2.is_available()


def test_empty_commit_handling():
    """Test that empty commits are handled gracefully."""
    with tempfile.TemporaryDirectory() as temp_dir:
        git_repo = GitRepo(Path(temp_dir))
        git_repo.init_repo()

        # Try to commit with no changes - should return True but not create commit
        initial_commits = len(list(git_repo.repo.walk(git_repo.repo.head.target)))

        result = git_repo.commit_changes("Empty commit test")
        assert result is True

        # Should not have created a new commit
        final_commits = len(list(git_repo.repo.walk(git_repo.repo.head.target)))
        assert final_commits == initial_commits


def test_commit_specific_files_only():
    """Test that only specified files are committed, not all changes."""
    with tempfile.TemporaryDirectory() as temp_dir:
        git_repo = GitRepo(Path(temp_dir))
        git_repo.init_repo()

        # Create multiple files
        imported_file = Path(temp_dir) / "chats" / "claude" / "imported.md"
        imported_file.parent.mkdir(parents=True, exist_ok=True)
        imported_file.write_text("# Imported conversation")

        manual_file = Path(temp_dir) / "journal" / "manual.md"
        manual_file.parent.mkdir(parents=True, exist_ok=True)
        manual_file.write_text("# Manual journal entry")

        # Commit only the imported file
        result = git_repo.commit_changes("Import conversations", files=[str(imported_file)])
        assert result is True

        # Check that manual file is still untracked
        status = git_repo.repo.status()
        # The manual file should appear as untracked (WT_NEW)
        manual_relative = "journal/manual.md"
        assert manual_relative in status
        assert status[manual_relative] & pygit2.GIT_STATUS_WT_NEW


def test_commit_multiple_specific_files():
    """Test committing multiple specific files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        git_repo = GitRepo(Path(temp_dir))
        git_repo.init_repo()

        # Create multiple imported files
        files_to_commit = []
        for i in range(3):
            file_path = Path(temp_dir) / "chats" / f"conversation_{i}.md"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"# Conversation {i}")
            files_to_commit.append(str(file_path))

        # Create unrelated file
        unrelated_file = Path(temp_dir) / "notes" / "unrelated.md"
        unrelated_file.parent.mkdir(parents=True, exist_ok=True)
        unrelated_file.write_text("# Unrelated note")

        # Commit only the conversation files
        result = git_repo.commit_changes("Import multiple conversations", files=files_to_commit)
        assert result is True

        # Check that unrelated file is still untracked
        status = git_repo.repo.status()
        assert "notes/unrelated.md" in status
