"""
Git integration for commonplace repositories.

Handles change tracking and commits for commonplace directories.
"""

from pathlib import Path
from typing import Optional

import pygit2

from commonplace import logger


class GitRepo:
    """Git repository manager for commonplace directories."""

    def __init__(self, path: Path) -> None:
        """Initialize git repo manager for given path."""
        self.path = path
        self.repo: Optional[pygit2.Repository] = None
        self._discover_repo()

    def _discover_repo(self) -> None:
        """Check if directory is already a git repository."""
        try:
            repo_path = pygit2.discover_repository(str(self.path))
            if repo_path:
                self.repo = pygit2.Repository(repo_path)
                logger.debug(f"Found git repository at {repo_path}")
        except Exception as e:
            logger.debug(f"No git repository found: {e}")

    def init_repo(self) -> bool:
        """
        Initialize a new git repository.

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.repo:
                logger.info("Directory is already a git repository")
                return True

            self.repo = pygit2.init_repository(str(self.path))
            logger.info(f"Initialized git repository at {self.path}")

            self._create_gitignore()
            self._create_initial_commit()
            return True

        except Exception as e:
            logger.error(f"Failed to initialize git repository: {e}")
            return False

    def _create_gitignore(self) -> None:
        """Create a sensible .gitignore for commonplace repositories."""
        gitignore_path = self.path / ".gitignore"
        gitignore_content = """# Python
__pycache__/
*.py[cod]
*.so
.Python
.venv/
venv/

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Temporary files
*~
.#*
\\#*#
.*.swp
.*.swo

# IDE
.vscode/
.idea/
*.sublime-*

# Commonplace specific
.env
*.tmp
*.temp
"""

        if not gitignore_path.exists():
            with open(gitignore_path, "w") as f:
                f.write(gitignore_content)
            logger.debug("Created .gitignore")

    def _create_initial_commit(self) -> None:
        """Create initial commit for new repositories."""
        if not self.repo:
            return

        try:
            # Add .gitignore to index
            self.repo.index.add(".gitignore")
            self.repo.index.write()

            # Create initial commit
            tree = self.repo.index.write_tree()
            signature = self._get_signature()

            self.repo.create_commit("HEAD", signature, signature, "Initial commit - commonplace repository", tree, [])
            logger.debug("Created initial commit")
        except Exception as e:
            logger.warning(f"Failed to create initial commit: {e}")

    def _get_signature(self) -> pygit2.Signature:
        """Get git signature for commits."""
        try:
            # Try to get configured git user
            config = pygit2.Config.get_global_config()
            name = config.get("user.name", "Commonplace User")
            email = config.get("user.email", "commonplace@localhost")
        except Exception:
            # Fallback if no git config
            name = "Commonplace User"
            email = "commonplace@localhost"

        return pygit2.Signature(name, email)

    def commit_changes(self, message: str, files: Optional[list[str]] = None) -> bool:
        """
        Commit changes to the repository.

        Args:
            message: Commit message
            files: Optional list of specific files to add. If None, adds all changes.

        Returns:
            True if commit was successful, False otherwise
        """
        if not self.repo:
            logger.debug("No git repository available for commit")
            return False

        try:
            # Add files to index
            if files:
                for file_path in files:
                    # Convert to relative path from repo root
                    rel_path = Path(file_path).relative_to(self.path)
                    self.repo.index.add(str(rel_path))
            else:
                # Add all changes
                self.repo.index.add_all()

            self.repo.index.write()

            # Check if there are any changes to commit
            tree = self.repo.index.write_tree()
            if self.repo.head_is_unborn:
                parent_commits = []
            else:
                parent_commits = [self.repo.head.target]
                # Check if tree is different from HEAD
                head_tree = self.repo[self.repo.head.target].tree
                if tree == head_tree.id:
                    logger.debug("No changes to commit")
                    return True

            # Create commit
            signature = self._get_signature()
            commit_id = self.repo.create_commit("HEAD", signature, signature, message, tree, parent_commits)

            logger.info(f"Created commit {str(commit_id)[:8]}: {message}")
            return True

        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            return False

    def is_available(self) -> bool:
        """Check if git repository is available."""
        return self.repo is not None
