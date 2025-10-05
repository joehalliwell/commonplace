import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from pygit2 import Diff, init_repository, Signature, Commit
from pygit2.enums import FileStatus
from pygit2.repository import Repository

from commonplace import logger
from commonplace._types import Note, Pathlike, RepoPath, RepoStats

from collections import defaultdict


@dataclass
class Commonplace:
    """
    Wraps a git repo
    """

    git: Repository

    @staticmethod
    def open(root: Path) -> "Commonplace":
        root = root.absolute()
        logger.info(f"Opening commonplace repository at {root}")
        git = Repository(root.as_posix())
        # Create .commonplace directory for embeddings and other data
        (root / ".commonplace").mkdir(exist_ok=True)
        return Commonplace(git=git)

    @staticmethod
    def init(root: Path):
        init_repository(root, bare=False)
        (root / ".commonplace").mkdir(exist_ok=True)

    @property
    def root(self) -> Path:
        """Get the root path of the repository."""
        return Path(self.git.workdir)

    @property
    def head_ref(self) -> str:
        """Get current HEAD tree SHA."""
        if self.git.head_is_unborn:
            # No commits yet - use a placeholder ref
            return "0" * 40
        return str(self.git.head.target)

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

        # Check if file exists and get its status
        try:
            flags = self.git.status_file(path.as_posix())
        except KeyError:
            # File doesn't exist yet (new file being created)
            return RepoPath(path=path, ref=self.head_ref)

        if flags != FileStatus.CURRENT:
            # File is modified/staged/new - not committed yet
            return RepoPath(path=path, ref=self.head_ref)

        # File is clean - find last commit that modified it (cached)
        path_map = self._build_path_commit_map(self.git.workdir)
        ref = path_map.get(path.as_posix(), self.head_ref)
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
        return self._read_note(repo_path)

    def _read_note(self, repo_path: RepoPath) -> Note:
        """
        Read note from disk.

        Currently only supports reading from working directory.
        Future: could read from git object store for historical refs.
        """
        logger.debug(f"Reading {repo_path}")
        abs_path = self.root / repo_path.path
        with open(abs_path) as fd:
            content = fd.read()
        return Note(repo_path=repo_path, content=content)

    def save(self, note: Note) -> None:
        """Save a note to working directory and stage."""
        abs_path = self.root / note.repo_path.path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as fd:
            fd.write(note.content)
        self.git.index.add(note.repo_path.path.as_posix())

    def commit(self, message: str) -> None:
        """Commit staged changes to the repository."""
        # FIXME: This doesn't work!
        if len(self.git.index) == 0:
            logger.info("No changes to commit")
            return
        author = Signature("Commonplace Bot", "commonplace@joehalliwell.com")
        committer = author
        tree = self.git.index.write_tree()
        self.git.create_commit(
            "HEAD",
            author,
            committer,
            message,
            tree,
            [self.git.head.target] if not self.git.head_is_unborn else [],
        )
        self.git.index.clear()
        logger.info(f"Committed changes with message: {message}")

    def stats(self) -> RepoStats:
        """Get repository statistics."""
        from datetime import datetime

        num_notes = 0
        total_size_bytes = 0
        num_per_type: dict[str, int] = defaultdict(int)
        oldest_timestamp = 0
        newest_timestamp = 0

        for rp in self.note_paths():
            num_notes += 1

            # Get file size
            total_size_bytes += (self.git.workdir / rp.path).stat().st_size

            # Extract provider from path (e.g., chats/claude/... -> "claude")
            parts = rp.path.parts
            if len(parts) < 2:
                continue
            if parts[0] == "chats" and len(parts) > 1:
                provider = parts[1]
                num_per_type[provider] = num_per_type.get(provider, 0) + 1
            else:
                provider = parts[0]
                num_per_type[provider] += 1

            # Extract timestamp from filename (YYYY-MM-DD-...)
            filename = rp.path.stem
            if len(filename) >= 10 and filename[4] == "-" and filename[7] == "-":
                try:
                    date_str = filename[:10]
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    timestamp = int(dt.timestamp())

                    if oldest_timestamp == 0 or timestamp < oldest_timestamp:
                        oldest_timestamp = timestamp
                    if newest_timestamp == 0 or timestamp > newest_timestamp:
                        newest_timestamp = timestamp
                except ValueError:
                    pass

        return RepoStats(
            num_notes=num_notes,
            total_size_bytes=total_size_bytes,
            num_per_type=num_per_type,
            oldest_timestamp=oldest_timestamp,
            newest_timestamp=newest_timestamp,
        )
