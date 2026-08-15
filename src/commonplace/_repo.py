import difflib
import hashlib
import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property, lru_cache
from pathlib import Path

from pygit2 import Commit, Diff, Signature, init_repository
from pygit2.enums import FileStatus, ObjectType
from pygit2.repository import Repository

from commonplace._config import DEFAULT_EDITOR, DEFAULT_NAME
from commonplace._logging import logger
from commonplace._types import Note, Pathlike, RepoPath

_INIT_GIT_IGNORE = """
# Commonplace

.commonplace/cache
.obsidian
.vscode
"""

_INIT_GIT_ATTRIBUTES = """
# Track blobs with Git LFS
.commonplace/blobs/** filter=lfs diff=lfs merge=lfs -text
"""

_INIT_CONFIG_TOML = f"""
# Commonplace configuration

# user = "{DEFAULT_NAME}"
# editor = "{DEFAULT_EDITOR}"
"""

_INIT_CLAUDE_SETTINGS = """\
{
  "extraKnownMarketplaces": {
    "commonplace": {
      "source": {
        "source": "github",
        "repo": "joehalliwell/commonplace"
      }
    }
  },
  "enabledPlugins": {
    "commonplace-skills@commonplace": true
  }
}
"""

_BOT_USERNAME = "Commonplace Bot"
_BOT_EMAIL = "commonplace@joehalliwell.com"


@dataclass(frozen=True)
class ConfigFile:
    """A config file `init` writes from a template and `doctor` checks is still there."""

    path: str
    template: str

    def divergence(self, existing: str) -> list[str]:
        """Report how `existing` differs from the template, if that is our business."""
        return []


@dataclass(frozen=True)
class UnmanagedConfig(ConfigFile):
    """Seeded once and then the user's own: we only care that it exists."""


@dataclass(frozen=True)
class ManagedLineConfig(ConfigFile):
    """
    Commonplace maintains the contents, so `doctor` reports any difference.

    This is how existing repos keep up as `init`'s templates evolve: print the
    diff and let the reader decide what to do about it. Deliberately no
    cleverer than that — no merging, no rewriting, no guessing which side is
    right.
    """

    def divergence(self, existing: str) -> list[str]:
        return list(
            difflib.unified_diff(
                self.template.splitlines(),
                existing.splitlines(),
                fromfile="template",
                tofile=self.path,
                lineterm="",
            )
        )


_CONFIG_TOML = UnmanagedConfig(".commonplace/config.toml", _INIT_CONFIG_TOML)
_GIT_IGNORE = ManagedLineConfig(".gitignore", _INIT_GIT_IGNORE)
_GIT_ATTRIBUTES = ManagedLineConfig(".gitattributes", _INIT_GIT_ATTRIBUTES)
_CLAUDE_SETTINGS = ManagedLineConfig(".claude/settings.json", _INIT_CLAUDE_SETTINGS)

_SCAFFOLDING: tuple[ConfigFile, ...] = (_CONFIG_TOML, _GIT_IGNORE, _GIT_ATTRIBUTES, _CLAUDE_SETTINGS)


@dataclass(frozen=True)
class DoctorReport:
    """What `doctor` put right, and what it wants a human to look at."""

    actions: list[str]
    warnings: list[str]


def _create_missing(root: Path, config: ConfigFile) -> bool:
    """Write the config file if it is absent. Returns True if it was created."""
    target = root / config.path
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(config.template)
    return True


def _hash_file(path: Path, buf_size: int = 65536) -> str:
    """SHA-256 hash a file, streaming in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(buf_size):
            h.update(chunk)
    return h.hexdigest()


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

    def store_blob(self, source_path: Path) -> RepoPath:
        """Store a file in .commonplace/blobs/ addressed by its SHA-256 hash.

        Returns the existing path if the blob already exists (idempotent).
        """
        self._ensure_gitattributes()

        digest = _hash_file(source_path)
        rel_path = Path(".commonplace") / "blobs" / digest / source_path.name
        abs_path = self.root / rel_path

        if not abs_path.exists():
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, abs_path)
            self.git.index.add(rel_path.as_posix())

        return self.make_repo_path(rel_path)

    def doctor(self) -> DoctorReport:
        """Restore missing scaffolding, and diff whatever has fallen behind `init`'s templates."""
        actions: list[str] = []
        warnings: list[str] = []

        for config in _SCAFFOLDING:
            if _create_missing(self.root, config):
                self.git.index.add(config.path)
                actions.append(f"Created {config.path}")
                continue

            divergence = config.divergence((self.root / config.path).read_text())
            if divergence:
                warnings.append(f"{config.path} differs from the template init now writes:\n" + "\n".join(divergence))

        if actions:
            self.git.index.write()

        return DoctorReport(actions=actions, warnings=warnings)

    def _ensure_gitattributes(self) -> None:
        """Create .gitattributes with LFS config if it doesn't exist yet."""
        if _create_missing(self.root, _GIT_ATTRIBUTES):
            self.git.index.add(_GIT_ATTRIBUTES.path)

    @cached_property
    def index(self):
        """Get the search index."""
        from commonplace._search._sqlite import SQLiteSearchIndex

        index_path = self.cache / "index.db"
        return SQLiteSearchIndex(index_path, is_live=self.is_live)

    def is_live(self, repo_path: RepoPath) -> bool:
        """
        Whether this exact version of a note is the one the repository holds now.

        False for a note that has been deleted, and for a version superseded by a
        later edit: either way the text indexed under that ref is no longer
        anywhere in the working tree, so quoting it back would be a lie.
        """
        if not (self.root / repo_path.path).exists():
            return False
        return self.make_repo_path(repo_path.path) == repo_path

    @staticmethod
    def init(root: Path):
        main = "refs/heads/main"

        # Create the git repository
        git = init_repository(root, bare=False, initial_head=main)

        # Lay down the scaffolding: stub config, .gitignore, LFS tracking for
        # blobs, and the Claude Code plugin marketplace. `doctor` checks the
        # same list, so the two can't drift apart.
        for scaffold in _SCAFFOLDING:
            _create_missing(root, scaffold)
            git.index.add(scaffold.path)  # type: ignore[attr-defined]

        # Create initial commit
        tree = git.index.write_tree()  # type: ignore[attr-defined]
        author = Signature(_BOT_USERNAME, _BOT_EMAIL)
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
        path_map = self._build_path_commit_map(self.git.workdir, head_ref)
        ref = path_map.get(path.as_posix(), head_ref)
        return RepoPath(path=path, ref=ref)

    @staticmethod
    @lru_cache(maxsize=1)
    def _build_path_commit_map(repo_dir: str, head_ref: str) -> dict[str, str]:
        """
        Build a map of all file paths to their last modifying commit.

        Walks the commit history once and builds the entire mapping.
        Cached by (repo_dir, head_ref) so we only walk once per HEAD state. The
        ref has to be part of the key: a commit moves HEAD, and a map built
        before it would go on reporting the superseded commit for every file
        that commit touched.

        Args:
            repo_dir: Repository path
            head_ref: Commit to walk back from, and the state this map describes

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
        last_commit = git[head_ref]
        assert isinstance(last_commit, Commit)
        remaining_files = set(walk_tree(last_commit.tree))

        for commit in git.walk(head_ref):
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

    def last_commit_time(self, pathspec: str, diff_filter: str | None = None) -> datetime | None:
        """UTC timestamp of the most recent commit touching `pathspec`, or
        None if no commit in history has touched it.

        Uses git author date (`%aI`) so timestamps are stable across
        rebases. Callers should be aware that this is commit time — always ≥
        the effective content timestamp of whatever was written.

        `diff_filter` maps directly to `git log --diff-filter=...` — pass e.g.
        `"AM"` to consider only commits that *added or modified* files under the
        pathspec, ignoring pure deletions or rename-source commits (important
        for fetch-cursor use, where `git mv chats/foo chats/bar` would
        otherwise poison the cursor for `chats/foo/`)."""
        import subprocess

        cmd = [
            "git",
            f"--git-dir={self.root / '.git'}",
            f"--work-tree={self.root}",
            "log",
            "-1",
            "--format=%aI",
        ]
        if diff_filter:
            cmd.append(f"--diff-filter={diff_filter}")
        cmd += ["--", pathspec]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        raw = result.stdout.strip()
        if not raw:
            return None
        # %aI carries the committer's local offset; fetchers work in UTC.
        return datetime.fromisoformat(raw).astimezone(UTC)

    def source(self, repo_path: RepoPath) -> str:
        """The source of this collection of notes/chats."""
        parts = repo_path.path.parts
        if len(parts) < 2:
            return "misc"
        if parts[0] == "chats":
            return "/".join(parts[:2])
        return parts[0]

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

    def commit(self, message: str, auto_index: bool | None = None) -> None:
        """Commit staged changes to the repository.

        Args:
            message: Commit message
            auto_index: Whether to index after committing (default: from config)
        """
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

        author = Signature(_BOT_USERNAME, _BOT_EMAIL)
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

        # Auto-index if enabled
        should_index = auto_index if auto_index is not None else self.config.auto_index
        if should_index:
            from commonplace._search._commands import index

            logger.info("Auto-indexing committed notes")
            index(self, rebuild=False)

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
        from datetime import datetime

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
                    timestamp = datetime.now(UTC).isoformat()
                    self._git(
                        "commit",
                        "-m",
                        f"Auto-commit before sync at {timestamp}",
                    )
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
            [
                "git",
                f"--git-dir={self.root / '.git'}",
                f"--work-tree={self.root}",
                "-c",
                f"user.name={_BOT_USERNAME}",
                "-c",
                f"user.email={_BOT_EMAIL}",
                *args,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
