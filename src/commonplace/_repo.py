import difflib
import hashlib
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property, lru_cache
from pathlib import Path

from commonplace._links import check_links, summarize
from commonplace._logging import logger
from commonplace._types import Note, Pathlike, RepoPath
from commonplace._utils import dump_frontmatter, load_frontmatter

# What `init` lays down, as it lands in a repo. Its dotfiles match nothing here, so they are inert.
_SCAFFOLD_ROOT = Path(__file__).parent / "resources" / "scaffold"

# Seeded once and then the user's; everything else in the scaffold is commonplace's to maintain.
_USER_OWNED = frozenset({".commonplace/config.toml", "index.md"})

_BOT_USERNAME = "Commonplace Bot"
_BOT_EMAIL = "commonplace@joehalliwell.com"

# Seconds to wait between attempts while another git process holds a lock.
_LOCK_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)

# Imports touch thousands of paths, more than argv holds.
_PATHSPEC_STDIN = ("--pathspec-from-file=-", "--pathspec-file-nul")


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


def _scaffold(path: str) -> ConfigFile:
    """The scaffold file at `path`, managed unless it becomes the user's."""
    kind = UnmanagedConfig if path in _USER_OWNED else ManagedLineConfig
    return kind(path, (_SCAFFOLD_ROOT / path).read_text())


_SCAFFOLDING: tuple[ConfigFile, ...] = tuple(
    _scaffold(file.relative_to(_SCAFFOLD_ROOT).as_posix())
    for file in sorted(_SCAFFOLD_ROOT.rglob("*"))
    if file.is_file()
)
_GIT_ATTRIBUTES = _scaffold(".gitattributes")


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


def _run_git(root: Path, *args: str, input: str | None = None) -> str:
    """Run git in `root` as the bot, waiting out another process's lock; returns stdout."""
    env = os.environ | {
        "LC_ALL": "C",
        "GIT_LITERAL_PATHSPECS": "1",
        "GIT_AUTHOR_NAME": _BOT_USERNAME,
        "GIT_AUTHOR_EMAIL": _BOT_EMAIL,
        "GIT_COMMITTER_NAME": _BOT_USERNAME,
        "GIT_COMMITTER_EMAIL": _BOT_EMAIL,
    }
    cmd = ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args]

    def run() -> str:
        return subprocess.run(
            cmd, input=input, capture_output=True, text=True, encoding="utf-8", check=True, env=env
        ).stdout

    for delay in _LOCK_RETRY_DELAYS:
        try:
            return run()
        except subprocess.CalledProcessError as e:
            if ".lock': File exists" not in e.stderr:
                raise
            logger.debug(f"Waiting {delay}s for a git lock: {e.stderr.strip()}")
            time.sleep(delay)
    return run()


def _changed(root: Path, paths: set[str], *diff_args: str) -> set[str]:
    """Those of `paths` that `git diff <diff_args>` reports."""
    return set(_run_git(root, "diff", "--name-only", "--no-renames", "-z", *diff_args).split("\0")) & paths


def _stage(root: Path, paths: set[str]) -> None:
    """Stage exactly `paths`, deletions included."""
    present = {p for p in paths if (root / p).exists()}
    if present:
        _run_git(root, "add", *_PATHSPEC_STDIN, input="\0".join(present))
    if paths - present:
        _run_git(root, "rm", "--cached", "-q", "--ignore-unmatch", *_PATHSPEC_STDIN, input="\0".join(paths - present))


def _commit(root: Path, paths: set[str], message: str) -> bool:
    """Commit exactly `paths`, re-staging once if a hook reformats them; False if there was nothing to commit."""
    try:
        _stage(root, paths)
        changed = _changed(root, paths, "--cached")
        if not changed:
            return False
        try:
            _run_git(root, "commit", "-q", "-m", message, *_PATHSPEC_STDIN, input="\0".join(changed))
        except subprocess.CalledProcessError:
            reformatted = _changed(root, changed)
            if not reformatted:
                raise
            logger.info(f"A hook rewrote {len(reformatted)} file(s); committing its version")
            _stage(root, reformatted)
            # The hook's version may be exactly what HEAD already has, as on a re-import.
            changed = _changed(root, changed, "--cached")
            if not changed:
                return False
            _run_git(root, "commit", "-q", "-m", message, *_PATHSPEC_STDIN, input="\0".join(changed))
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Commit failed:\n{e.stdout}{e.stderr}".strip()) from e
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

    root: Path
    # Paths written since the last commit: the only ones the next commit may touch.
    _pending: set[str] = field(default_factory=set, repr=False)

    @staticmethod
    def open(root: Path) -> "Commonplace":
        logger.debug(f"Opening commonplace repository at {root}")
        try:
            toplevel = Path(_run_git(root, "rev-parse", "--show-toplevel").strip())
        except subprocess.CalledProcessError as e:
            raise ValueError(f"{root} is not in a git repository") from e
        if toplevel != root.resolve():
            raise ValueError(f"{root} is not the root of its git repository, {toplevel}")
        try:
            _run_git(toplevel, "rev-parse", "--verify", "-q", "HEAD")
        except subprocess.CalledProcessError as e:
            raise ValueError("Repository has no commits yet") from e
        return Commonplace(root=toplevel)

    def close(self):
        """Close this repo. Does nothing."""

    @cached_property
    def config(self):
        """Get the commonplace configuration."""
        from commonplace._config import Config

        return Config.load(self.root)

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
            self._pending.add(rel_path.as_posix())

        return self.make_repo_path(rel_path)

    def doctor(self) -> DoctorReport:
        """Restore and commit missing scaffolding, diff whatever has fallen behind `init`'s templates, and find broken links."""
        actions: list[str] = []
        warnings: list[str] = []

        for config in _SCAFFOLDING:
            if _create_missing(self.root, config):
                self._pending.add(config.path)
                actions.append(f"Created {config.path}")
                continue

            divergence = config.divergence((self.root / config.path).read_text())
            if divergence:
                warnings.append(f"{config.path} differs from the template init now writes:\n" + "\n".join(divergence))

        warnings.extend(summarize(check_links(self.root, list(self.paths()))))

        if actions:
            self.commit("Restore scaffolding", auto_index=False)

        return DoctorReport(actions=actions, warnings=warnings)

    def _ensure_gitattributes(self) -> None:
        """Create .gitattributes with LFS config if it doesn't exist yet."""
        if _create_missing(self.root, _GIT_ATTRIBUTES):
            self._pending.add(_GIT_ATTRIBUTES.path)

    @cached_property
    def index(self):
        """Get the search index."""
        from commonplace._search._sqlite import SQLiteSearchIndex

        index_path = self.cache / "index.db"
        return SQLiteSearchIndex(index_path, note_exists=self.note_exists)

    def note_exists(self, repo_path: RepoPath) -> bool:
        """
        Whether the note a chunk came from is still in the repository.

        Deliberately blind to which version: an edited note is still there to
        open, so a chunk of its previous text is worth returning until indexing
        catches up. A deleted one is not, and quoting it back would be a lie.
        """
        return (self.root / repo_path.path).exists()

    @staticmethod
    def init(root: Path):
        root.mkdir(parents=True, exist_ok=True)
        _run_git(root, "init", "-q", "--initial-branch=main")

        # `doctor` checks the same list, so the two can't drift apart.
        for scaffold in _SCAFFOLDING:
            _create_missing(root, scaffold)

        _commit(root, {scaffold.path for scaffold in _SCAFFOLDING}, "Initial commit")

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
            path = path.relative_to(self.root, walk_up=False)
        return self._repo_path(path, *self._status(path.as_posix()))

    def _status(self, *pathspec: str, untracked: bool = False) -> tuple[str, set[str]]:
        """HEAD, and which files under `pathspec` differ from it (untracked ones only if asked), from one `git status`."""
        untracked_files = "--untracked-files=all" if untracked else "--untracked-files=no"
        out = self._git("status", "--porcelain=v2", "-z", "--branch", untracked_files, "--no-renames", "--", *pathspec)
        head, dirty = "", set()
        for entry in out.split("\0"):
            if entry.startswith("# branch.oid "):
                head = entry.removeprefix("# branch.oid ")
            elif entry.startswith("1 "):
                dirty.add(entry.split(" ", 8)[8])
            elif entry.startswith("u "):
                dirty.add(entry.split(" ", 10)[10])
            elif entry.startswith("? "):
                dirty.add(entry.removeprefix("? "))
        return head, dirty

    def _repo_path(self, path: Path, head: str, dirty: set[str]) -> RepoPath:
        """The commit that last changed `path`, or HEAD if it is uncommitted or changed since."""
        if path.as_posix() in dirty:
            return RepoPath(path=path, ref=head)
        return RepoPath(path=path, ref=self._build_path_commit_map(str(self.root), head).get(path.as_posix(), head))

    @staticmethod
    @lru_cache(maxsize=1)
    def _build_path_commit_map(repo_dir: str, head_ref: str) -> dict[str, str]:
        """
        Map every path in the history of `head_ref` to the newest commit that changed it.

        One `git log` pass, cached by (repo_dir, head_ref). The ref has to be
        part of the key: a commit moves HEAD, and a map built before it would
        go on reporting the superseded commit for every file that commit touched.
        """
        out = _run_git(Path(repo_dir), "log", "--format=%x00%H", "--name-only", "-z", "--no-renames", head_ref)
        # Each commit is an empty token, its hash, then the paths it changed.
        path_to_commit: dict[str, str] = {}
        tokens = iter(out.split("\0"))
        commit = ""
        for token in tokens:
            if not token:
                commit = next(tokens, "")
            else:
                path_to_commit.setdefault(token.lstrip("\n"), commit)
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
        args = ["log", "-1", "--format=%aI"]
        if diff_filter:
            args.append(f"--diff-filter={diff_filter}")
        raw = self._git(*args, "--", pathspec).strip()
        if not raw:
            return None
        # %aI carries the committer's local offset; fetchers work in UTC.
        return datetime.fromisoformat(raw).astimezone(UTC)

    def source(self, repo_path: RepoPath) -> str:
        """The source of this collection of notes/chats."""
        parts = repo_path.path.parts
        if len(parts) < 2:
            return "misc"
        if parts[0] in ("chats", "memory"):
            return "/".join(parts[:2])
        return parts[0]

    def notes(self) -> Iterator[Note]:
        """Get an iterator over all notes at current HEAD."""
        for repo_path in self.note_paths():
            yield self.load(repo_path)

    def paths(self) -> Iterator[Path]:
        """Every file in the working tree that git would share, relative to the root, skipping dot-directories."""
        out = self._git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
        for path in sorted({Path(p) for p in out.split("\0") if p}):
            if not any(part.startswith(".") for part in path.parts[:-1]) and (self.root / path).exists():
                yield path

    def note_paths(self) -> Iterator[RepoPath]:
        """Get an iterator over all note paths at current HEAD, skipping dot-directories."""
        head, dirty = self._status()
        for path in self.paths():
            if path.suffix == ".md":
                yield self._repo_path(path, head, dirty)

    def load(self, repo_path: RepoPath) -> Note:
        """
        Fetch a note at a specific repository location.

        Args:
            repo_path: The repository path to fetch

        Returns:
            Note object with its metadata and body
        """
        logger.debug(f"Fetching note at {repo_path}")
        abs_path = self.root / repo_path.path

        with open(abs_path) as fd:
            metadata, body = load_frontmatter(fd.read())
        return Note(repo_path=repo_path, body=body, metadata=metadata)

    def save(self, note: Note) -> None:
        """Save a note to working directory for the next commit. Beware! This will overwrite
        existing content."""
        abs_path = self.root / note.repo_path.path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as fd:
            fd.write(dump_frontmatter(note.metadata, note.body))
        self._pending.add(note.repo_path.path.as_posix())

    def remove(self, path: Path) -> None:
        """Delete a file from the working directory, for the next commit."""
        (self.root / path).unlink()
        self._pending.add(path.as_posix())

    def commit(self, message: str, auto_index: bool | None = None) -> None:
        """Commit what this repo has saved, removed or stored since the last commit, and nothing else.

        Args:
            message: Commit message
            auto_index: Whether to index after committing (default: from config)
        """
        committed = _commit(self.root, self._pending, message)
        self._pending.clear()
        if not committed:
            logger.info("No changes to commit")
            return
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
        return remote_name in self._git("remote").split()

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
            # The one commit of work commonplace didn't write: the user's own edits, whatever they are.
            _, changed = self._status(untracked=True)
            if changed:
                logger.info("Adding and committing changes...")
                try:
                    _commit(self.root, changed, f"Auto-commit before sync at {datetime.now(UTC).isoformat()}")
                except RuntimeError as e:
                    raise ValueError(f"Failed to commit changes. {e}") from e

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
        return _run_git(self.root, *args)
