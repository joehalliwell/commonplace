import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from pygit2 import init_repository, Signature
from pygit2.enums import FileStatus
from pygit2.repository import Repository

from commonplace import logger
from commonplace._types import Note, Pathlike, RepoPath, RepoStats


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
        rel_path = self._rel_path(path)

        # Check if file exists and get its status
        try:
            flags = self.git.status_file(rel_path.as_posix())
        except KeyError:
            # File doesn't exist yet (new file being created)
            return RepoPath(path=rel_path, ref=self.head_ref)

        if flags != FileStatus.CURRENT:
            # File is modified/staged/new - not committed yet
            return RepoPath(path=rel_path, ref=self.head_ref)

        # File is clean - find last commit that modified it (cached)
        ref = self._find_last_commit_for_path(self.git.workdir, rel_path.as_posix(), self.head_ref)
        return RepoPath(path=rel_path, ref=ref)

    @staticmethod
    @lru_cache(maxsize=4096)
    def _find_last_commit_for_path(repo_dir: str, path_str: str, head_ref: str) -> str:
        """
        Find the last commit that modified a file.

        Cached by (repo_dir, path, head_ref) to avoid redundant history walks.
        Static method to ensure cache doesn't hold references to self.

        Args:
            repo_dir: Repository path
            path_str: Path as string (relative to repo root)
            head_ref: Current HEAD ref

        Returns:
            Commit SHA that last modified the file
        """
        # Reopen repository (cheap operation, just loads metadata)
        git = Repository(repo_dir)

        try:
            last_commit = None

            for commit in git.walk(git.head.target):
                # Check if file was modified in this commit
                if len(commit.parents) == 0:
                    # Initial commit - check if file exists
                    try:
                        commit.tree[path_str]
                        last_commit = commit
                    except KeyError:
                        pass
                    break
                else:
                    # Check if this commit modified the file
                    parent = commit.parents[0]
                    try:
                        current_entry = commit.tree[path_str]
                        try:
                            parent_entry = parent.tree[path_str]
                            # File exists in both - check if content changed
                            if current_entry.id != parent_entry.id:
                                last_commit = commit
                                break
                        except KeyError:
                            # File doesn't exist in parent - was added here
                            last_commit = commit
                            break
                    except KeyError:
                        # File doesn't exist in this commit - keep looking
                        continue

            return str(last_commit.id) if last_commit else head_ref
        except Exception as e:
            # Fallback to HEAD if we can't determine
            logger.warning(f"Could not determine last commit for {path_str}: {e}, using HEAD")
            return head_ref

    def notes(self) -> Iterator[Note]:
        """Get an iterator over all notes at current HEAD."""
        for root, dirs, files in os.walk(self.git.workdir):
            for f in files:
                abs_path = Path(root) / f
                if self.git.path_is_ignored(abs_path.as_posix()):
                    continue
                if abs_path.suffix != ".md":
                    continue
                try:
                    repo_path = self.make_repo_path(abs_path)
                    yield self.get_note(repo_path)
                except Exception:
                    logger.warning(f"Can't parse {abs_path}")

    def note_paths(self) -> Iterator[RepoPath]:
        """Get an iterator over all note paths at current HEAD."""
        for root, _, files in os.walk(self.git.workdir):
            for f in files:
                abs_path = Path(root) / f
                if self.git.path_is_ignored(abs_path.as_posix()):
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

    def _rel_path(self, path: Pathlike) -> Path:
        """
        Returns a relative path to the note within the repository.

        Args:
            path (Pathlike): Path to the note, can be absolute or relative.

        Returns:
            Path: Path relative to the repository root.

        Raises:
            ValueError: If the path is not relative to the repository root.
        """
        path = Path(path)
        if path.is_absolute():
            return path.relative_to(self.git.workdir, walk_up=False)
        return path

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
        num_notes = sum(1 for _ in self.note_paths())
        return RepoStats(num_notes=num_notes)
