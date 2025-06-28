import tempfile
from pathlib import Path
from commonplace._git import GitRepo


class TestGitRepo:
    def test_init_new_repo(self):
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

    def test_init_existing_repo(self):
        """Test initializing when repository already exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            git_repo = GitRepo(Path(temp_dir))

            # Initialize repo twice
            assert git_repo.init_repo() is True
            assert git_repo.init_repo() is True  # Should not fail

    def test_commit_changes(self):
        """Test committing changes to repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            git_repo = GitRepo(Path(temp_dir))
            git_repo.init_repo()

            # Create a test file
            test_file = Path(temp_dir) / "test.md"
            test_file.write_text("# Test content")

            # Commit the change
            assert git_repo.commit_changes("Add test file") is True

    def test_no_commit_without_repo(self):
        """Test that commit fails gracefully without repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            git_repo = GitRepo(Path(temp_dir))

            # Should not be able to commit without repo
            assert git_repo.commit_changes("Test commit") is False

    def test_discover_existing_repo(self):
        """Test discovering an existing repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Initialize repo manually first
            git_repo1 = GitRepo(Path(temp_dir))
            git_repo1.init_repo()

            # Create new GitRepo instance - should discover existing repo
            git_repo2 = GitRepo(Path(temp_dir))
            assert git_repo2.is_available()

    def test_empty_commit_handling(self):
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
