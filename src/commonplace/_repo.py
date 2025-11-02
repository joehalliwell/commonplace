import os
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Iterator

from pygit2 import Commit, Diff, Signature, init_repository
from pygit2.enums import FileStatus, ObjectType
from pygit2.repository import Repository

from commonplace._config import DEFAULT_EDITOR, DEFAULT_NAME
from commonplace._logging import logger
from commonplace._types import Note, Pathlike, RepoPath

_INIT_GIT_IGNORE = """
# Commonplace

.commonplace/cache
"""

_INIT_CONFIG_TOML = f"""
# Commonplace configuration

# user = "{DEFAULT_NAME}"
# editor = "{DEFAULT_EDITOR}"
"""


@dataclass
class Commonplace:
    """
    Simplified and opinionated abstraction around a git repo with a
    configuration and search index.
    """

    git: Repository

    @staticmethod
    def open(root: Path) -> "Commonplace":
        root = root.absolute()
        logger.debug(f"Opening commonplace repository at {root}")
        git = Repository(root.as_posix())
        assert not git.head_is_unborn, "Repository has no commits yet"
        return Commonplace(git=git)

    def close(self):
        """Close this repo. Does nothing."""
        ...

    @cached_property
    def root(self) -> Path:
        """Get the root path of the repository."""
        return Path(self.git.workdir)

    @cached_property
    def config(self):
        """Get the commonplace configuration."""
        from commonplace._config import Config

        return Config()

    @cached_property
    def cache(self) -> Path:
        """Get the cache directory."""
        return self.root / ".commonplace" / "cache"

    @cached_property
    def index(self):
        """Get the search index."""
        from commonplace._search._sqlite import SQLiteSearchIndex

        index_path = self.cache / "index.db"
        try:
            return SQLiteSearchIndex(index_path)
        except Exception as e:
            logger.error(f"Search index not found at '{index_path}'.")
            raise SystemExit(1) from e

    @staticmethod
    def init(root: Path):
        main = "refs/heads/main"

        # Create the git repository
        git = init_repository(root, bare=False, initial_head=main)

        # Create stub config
        config_path = root / ".commonplace"
        config_path.mkdir(exist_ok=True, parents=True)
        config_toml_path = config_path / "config.toml"

        if not config_toml_path.exists():
            config_toml_path.write_text(_INIT_CONFIG_TOML)
        git.index.add(config_toml_path.relative_to(root))  # type: ignore[attr-defined]

        # Create initial .gitignore
        gitignore_path = root / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(_INIT_GIT_IGNORE)
        git.index.add(gitignore_path.relative_to(root))  # type: ignore[attr-defined]

        # Create initial commit
        tree = git.index.write_tree()  # type: ignore[attr-defined]
        author = Signature("Commonplace Bot", "commonplace@joehalliwell.com")
        git.create_commit(
            main,
            author,
            author,
            "Initial commit",
            tree,
            [],  # No parents for initial commit
        )

        # Checkout the main branch to ensure HEAD is a symbolic reference
        git.index.write()  # type: ignore[attr-defined]
        git.checkout(main)  # type: ignore[attr-defined]

    def make_repo_path(self, path: Pathlike) -> RepoPath:
        """
        Create a RepoPath for a file with the commit that last modified it.

        Args:
            path: Absolute or relative path

        Returns:
            RepoPath with relative path and last-modified commit ref
        """

        path = Path(path)
        if path.is_absolute():
            path = path.relative_to(self.git.workdir, walk_up=False)

        head_ref = str(self.git.head.target)

        # Check if file exists and get its status
        try:
            flags = self.git.status_file(path.as_posix())
        except KeyError:
            # File doesn't exist yet (new file being created)
            return RepoPath(path=path, ref=head_ref)

        if flags != FileStatus.CURRENT:
            # File is modified/staged/new - not committed yet
            return RepoPath(path=path, ref=head_ref)

        # File is clean - find last commit that modified it (cached)
        path_map = self._build_path_commit_map(self.git.workdir)
        ref = path_map.get(path.as_posix(), head_ref)
        return RepoPath(path=path, ref=ref)

    @staticmethod
    @lru_cache(maxsize=1)
    def _build_path_commit_map(repo_dir: str) -> dict[str, str]:
        """
        Build a map of all file paths to their last modifying commit.

        Walks the commit history once and builds the entire mapping.
        Cached by (repo_dir, head_ref) so we only walk once per HEAD state.

        Args:
            repo_dir: Repository path
            head_ref: Current HEAD ref

        Returns:
            Dict mapping file paths to commit SHAs
        """
        # Reopen repository (cheap operation, just loads metadata)
        git = Repository(repo_dir)
        path_to_commit: dict[str, str] = {}

        if git.head_is_unborn:
            return path_to_commit

        def walk_tree(tree, prefix=""):
            """Recursively walk tree and yield all file paths."""
            for entry in tree:
                path = f"{prefix}{entry.name}" if prefix else entry.name
                if entry.type_str == "tree":
                    # Recurse into subdirectory
                    yield from walk_tree(git[entry.id], f"{path}/")
                else:
                    yield path

        # Get all files at HEAD - this is what we need to find commits for
        last_commit = git[git.head.target]
        assert isinstance(last_commit, Commit)
        remaining_files = set(walk_tree(last_commit.tree))

        for commit in git.walk(git.head.target):
            if not remaining_files:
                # Found commits for all files, can stop early
                break

            if not commit.parents:
                # Initial commit - record all remaining files
                for path in remaining_files:
                    path_to_commit[path] = str(commit.id)
                break

            # Get diff to find what files changed in this commit
            parent = commit.parents[0]
            diff = git.diff(parent, commit)
            assert isinstance(diff, Diff)

            # Record each changed file and remove from remaining set
            for delta in diff.deltas:
                path = delta.new_file.path
                if path in remaining_files:
                    path_to_commit[path] = str(commit.id)
                    remaining_files.remove(path)

        return path_to_commit

    def notes(self) -> Iterator[Note]:
        """Get an iterator over all notes at current HEAD."""
        for repo_path in self.note_paths():
            yield self.get_note(repo_path)

    def note_paths(self) -> Iterator[RepoPath]:
        """Get an iterator over all note paths at current HEAD."""
        for root, _, files in os.walk(self.git.workdir):
            for f in files:
                abs_path = Path(root) / f
                if self.git.path_is_ignored(abs_path.as_posix()):
                    continue
                if abs_path.suffix != ".md":
                    continue
                yield self.make_repo_path(abs_path)

    def get_note(self, repo_path: RepoPath) -> Note:
        """
        Fetch a note at a specific repository location.

        Args:
            repo_path: The repository path to fetch

        Returns:
            Note object with content
        """
        logger.debug(f"Fetching note at {repo_path}")
        abs_path = self.root / repo_path.path

        with open(abs_path) as fd:
            content = fd.read()
        return Note(repo_path=repo_path, content=content)

    def save(self, note: Note) -> None:
        """Save a note to working directory and stage. Beware! This will overwrite
        existing content."""
        abs_path = self.root / note.repo_path.path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as fd:
            fd.write(note.content)
        self.git.index.add(note.repo_path.path.as_posix())

    def commit(self, message: str) -> None:
        """Commit staged changes to the repository."""
        # Check if there are actually changes to commit
        tree = self.git.index.write_tree()

        if self.git.head_is_unborn:
            # No commits yet - commit if index has any entries
            has_changes = len(self.git.index) > 0
        else:
            # Compare index tree with HEAD tree to detect changes
            head_commit = self.git.head.peel(ObjectType.COMMIT)
            assert isinstance(head_commit, Commit)
            head_tree = head_commit.tree.id
            has_changes = tree != head_tree

        if not has_changes:
            logger.info("No changes to commit")
            return

        author = Signature("Commonplace Bot", "commonplace@joehalliwell.com")
        committer = author
        self.git.create_commit(
            "HEAD",
            author,
            committer,
            message,
            tree,
            [self.git.head.target] if not self.git.head_is_unborn else [],
        )
        # Write index to disk to ensure it matches the new HEAD
        self.git.index.write()
        logger.info(f"Committed changes with message: {message}")

    def has_remote(self, remote_name: str = "origin") -> bool:
        """
        Check if a remote exists.

        Args:
            remote_name: Name of the remote to check

        Returns:
            True if remote exists, False otherwise
        """
        try:
            self.git.remotes[remote_name]
            return True
        except KeyError:
            return False

    def sync(
        self,
        remote_name: str = "origin",
        branch: str | None = None,
        strategy: str = "rebase",
        auto_commit: bool = True,
    ) -> None:
        """
        Synchronize repository with remote using git commands.

        Steps:
        1. Check for remote
        2. Add and commit all changes (if auto_commit=True)
        3. Pull from remote (rebase or merge)
        4. Push to remote

        Args:
            remote_name: Name of remote (default: "origin")
            branch: Branch name (default: current branch)
            strategy: "rebase" or "merge" (default: "rebase")
            auto_commit: Auto-commit uncommitted changes (default: True)

        Raises:
            ValueError: If sync operation fails
        """
        import subprocess
        from datetime import datetime, timezone

        # 1. Check for remote (helpful error message)
        if not self.has_remote(remote_name):
            raise ValueError(f"Remote '{remote_name}' not found. Add remote first.")

        # Get current branch if not specified
        if branch is None:
            try:
                result = self._git("rev-parse", "--abbrev-ref", "HEAD")
                branch = result.strip()
            except subprocess.CalledProcessError:
                raise ValueError("Could not determine current branch.")

        logger.info(f"Syncing branch '{branch}' with '{remote_name}'")

        # 2. Auto-commit if there are changes
        if auto_commit:
            try:
                # Check if there are changes
                result = self._git("status", "--porcelain")
                if result.strip():
                    logger.info("Adding and committing changes...")
                    self._git("add", "-A")
                    timestamp = datetime.now(timezone.utc).isoformat()
                    self._git("commit", "-m", f"Auto-commit before sync at {timestamp}")
            except subprocess.CalledProcessError as e:
                raise ValueError(f"Failed to commit changes. {e.stderr}") from e

        # 3. Pull from remote (skip if remote branch doesn't exist yet)
        logger.info(f"Pulling from {remote_name}/{branch}...")
        pull_args = ["pull", remote_name, branch]
        if strategy == "rebase":
            pull_args.append("--rebase")
        try:
            self._git(*pull_args)
        except subprocess.CalledProcessError as e:
            # If remote branch doesn't exist, this is a first push - skip pull
            if "couldn't find remote ref" in (e.stderr or ""):
                logger.info(f"Remote branch {remote_name}/{branch} doesn't exist yet (first push)")
            else:
                stderr = e.stderr.strip() if e.stderr else ""
                raise ValueError(f"Failed to pull from {remote_name}/{branch}. {stderr}") from e

        # 4. Push to remote
        logger.info(f"Pushing to {remote_name}/{branch}...")
        try:
            self._git("push", remote_name, branch)
            logger.info(f"Successfully synced with {remote_name}/{branch}")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else ""
            raise ValueError(f"Failed to push to {remote_name}/{branch}. {stderr}") from e

    def _git(self, *args: str) -> str:
        """
        Run a git command in the repository.

        Args:
            *args: Git command arguments

        Returns:
            Command output (stdout)

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        import subprocess

        result = subprocess.run(
            ["git", f"--git-dir={self.root / '.git'}", f"--work-tree={self.root}", *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
