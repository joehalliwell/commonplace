import tempfile
from pathlib import Path
import pygit2
from commonplace._git import GitRepo


class TestGitSelectiveCommit:
    def test_commit_specific_files_only(self):
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

    def test_commit_multiple_specific_files(self):
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
