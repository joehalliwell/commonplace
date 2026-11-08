"""The commonplace's git repository, and the one way anything reaches it.

Every git operation goes through the git CLI via `_run_git`, never a library: re-implementing the porcelain cost
a silent revert (#102). Every operation that writes commits what it wrote: `save`, `remove` and `store_blob`
record their paths, `commit` stages and commits exactly those, and nothing else touches the index. Commits run
the user's hooks.
"""

import hashlib
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Collection, Iterable, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from functools import cached_property, lru_cache
from pathlib import Path

from commonplace._config import BLOBS, CACHE, MARGINALIA
from commonplace._links import BrokenLink, Edge, Files, Target, UnresolvedNote
from commonplace._logging import logger
from commonplace._marginalia import read_marginalia, write_marginalia
from commonplace._scaffold import TEMPLATES, lay_down
from commonplace._types import Blob, Marginalia, Note, Pathlike, RepoPath
from commonplace._utils import dump_frontmatter, load_frontmatter

_BOT_USERNAME = "Commonplace Bot"
_BOT_EMAIL = "commonplace@joehalliwell.com"

# Seconds to wait between attempts while another git process holds a lock.
_LOCK_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)

# Imports touch thousands of paths, more than argv holds.
_PATHSPEC_STDIN = ("--pathspec-from-file=-", "--pathspec-file-nul")


def _run_git(root: Path, *args: str, input: str | None = None, as_user: bool = False) -> str:
    """Run git in `root` as the bot, or as the user's own git identity, waiting out another process's lock."""
    env = os.environ | {"LC_ALL": "C", "GIT_LITERAL_PATHSPECS": "1"}
    if not as_user:
        env |= {
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


def _commit(root: Path, paths: set[str], message: str, as_user: bool = False) -> bool:
    """Commit exactly `paths`, re-staging once if a hook reformats them; False if there was nothing to commit."""
    try:
        _stage(root, paths)
        changed = _changed(root, paths, "--cached")
        if not changed:
            return False
        try:
            _run_git(root, "commit", "-q", "-m", message, *_PATHSPEC_STDIN, input="\0".join(changed), as_user=as_user)
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
            _run_git(root, "commit", "-q", "-m", message, *_PATHSPEC_STDIN, input="\0".join(changed), as_user=as_user)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Commit failed:\n{e.stdout}{e.stderr}".strip()) from e
    return True


@lru_cache(maxsize=4)
def _last_changed(root: Path, head: str, pathspec: str, field: str) -> dict[str, str]:
    """Each path under `pathspec` in `head`'s history, newest first, with `field` of the last commit to change it.

    Keyed by `head`, since a commit moves it and a map built before would go on reporting the superseded commit.
    """
    out = _run_git(root, "log", f"--format=%x00>{field}", "--name-only", "-z", "--no-renames", head, "--", pathspec)
    # Each commit is an empty token, its field after a `>` so it is never empty, then the paths it changed.
    last: dict[str, str] = {}
    tokens = iter(out.split("\0"))
    value = ""
    for token in tokens:
        if not token:
            value = next(tokens, "")[1:]
        else:
            last.setdefault(token.lstrip("\n"), value)
    return last


def _hash_file(path: Path, buf_size: int = 65536) -> str:
    """SHA-256 hash a file, streaming in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(buf_size):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Commonplace:
    """A git repository of notes, with configuration and search index in `.commonplace/`; it corresponds to an OKF bundle."""

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
        return self.root / CACHE

    def store_blob(self, source_path: Path) -> RepoPath:
        """Store a file in .commonplace/blobs/ addressed by its SHA-256 hash.

        Returns the existing path if the blob already exists (idempotent).
        """
        digest = _hash_file(source_path)
        rel_path = BLOBS / digest / source_path.name
        abs_path = self.root / rel_path

        if not abs_path.exists():
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, abs_path)
            self._wrote(rel_path)

        return self.make_repo_path(rel_path)

    @cached_property
    def index(self):
        """Get the search index."""
        from commonplace._search._sqlite import SQLiteSearchIndex

        index_path = self.cache / "index.db"
        return SQLiteSearchIndex(
            index_path,
            note_exists=self.note_exists,
            is_hidden=lambda path: self.load(RepoPath(path)).hidden,
        )

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

        lay_down(root)
        _commit(root, set(TEMPLATES), "Initial commit")

    def make_repo_path(self, path: Pathlike) -> RepoPath:
        """A committed file's RepoPath, at the commit that last changed it; a note being written needs no ref."""
        path = Path(path)
        if path.is_absolute():
            path = path.relative_to(self.root, walk_up=False)
        return self._repo_paths([path])[0]

    def _repo_paths(self, paths: list[Path]) -> list[RepoPath]:
        """Each of `paths` at the commit that last changed it, uncommitted changes aside, or HEAD if none has."""
        head = self._head()
        last = _last_changed(self.root, head, ".", "%H")
        return [RepoPath(path, last.get(path.as_posix(), head)) for path in paths]

    def _head(self) -> str:
        return self._git("rev-parse", "HEAD").strip()

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

    def last_subjects(self, pathspec: str) -> dict[str, str]:
        """Each committed path under `pathspec`, with the subject of the last commit that changed it."""
        return dict(_last_changed(self.root, self._head(), pathspec, "%s"))

    def uncommitted(self, pathspec: str) -> set[str]:
        """Paths under `pathspec` that differ from HEAD, untracked ones included."""
        tracked = self._git("diff", "--name-only", "--no-renames", "-z", "HEAD", "--", pathspec)
        untracked = self._git("ls-files", "--others", "--exclude-standard", "-z", "--", pathspec)
        return set(f"{tracked}\0{untracked}".split("\0")) - {""}

    def paths(self) -> Iterator[Path]:
        """Every file in the working tree that git would share, relative to the root, skipping dot-directories."""
        for path in sorted(map(Path, self._ls("."))):
            if not any(part.startswith(".") for part in path.parts[:-1]):
                yield path

    def _ls(self, pathspec: str) -> set[str]:
        """The files under `pathspec` in the working tree that git would share, tracked or not."""
        out = self._git("ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", pathspec)
        return {path for path in out.split("\0") if path and (self.root / path).exists()}

    def history(self, path: Path) -> list[tuple[str, str]]:
        """The commits that changed `path`, newest first, following renames, as (date, subject)."""
        out = self._git("log", "--follow", "--format=%as%x00%s", "--", path.as_posix())
        return [tuple(line.split("\0", 1)) for line in out.splitlines() if "\0" in line]  # type: ignore[misc]

    def renamed_since(self, ref: str) -> dict[Path, Path]:
        """Where each file `ref` had has moved to by HEAD, as git's rename detection sees it."""
        fields = self._git("diff", "-M", "--name-status", "-z", "--diff-filter=R", ref, "HEAD").split("\0")
        # -z gives status, old path, new path for each rename.
        return {Path(fields[i + 1]): Path(fields[i + 2]) for i in range(0, len(fields) - 2, 3)}

    def note_paths(self) -> Iterator[RepoPath]:
        """Get an iterator over all note paths at current HEAD, skipping dot-directories."""
        return iter(self._repo_paths([path for path in self.paths() if path.suffix == ".md"]))

    def load(self, repo_path: RepoPath) -> Note:
        """The note at `repo_path`, as the working tree has it, with its marginalia; one that's gone reads as empty."""
        logger.debug(f"Fetching note at {repo_path}")
        path = self.root / repo_path.path
        text = path.read_text(errors="replace") if repo_path.path.suffix == ".md" and path.exists() else ""
        metadata, body = load_frontmatter(text)
        marginalia = read_marginalia(self.root, repo_path.path)
        from commonplace._sources import source_holding, source_named

        # The source the note names, or failing that the one whose tree holds it.
        source = source_named(metadata.get("source")) or source_holding(repo_path.path)
        return Note(repo_path, body, metadata, marginalia=marginalia, text=text, source=source)

    def save(self, note: Note) -> None:
        """Save a note to working directory for the next commit. Beware! This will overwrite
        existing content."""
        abs_path = self.root / note.repo_path.path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as fd:
            fd.write(dump_frontmatter(note.metadata, note.body))
        self._wrote(note.repo_path.path)

    def remove(self, path: Path) -> None:
        """Delete a file from the working directory, for the next commit."""
        (self.root / path).unlink()
        self._wrote(path)

    def _wrote(self, path: Path) -> None:
        """Hold `path` for the next commit, and drop the graph read before it changed."""
        self._pending.add(path.as_posix())
        self.__dict__.pop("files", None)

    # --- The repository as a graph: each file a node, its path its id, each link a note makes an edge ---

    def holds(self, note: Note, aside: Collection[str] = ()) -> bool:
        """Whether the working tree holds `note` already: its frontmatter, keys `aside` aside, and its words, since a
        formatting hook may rewrap or reindent what was written."""
        held = self.load(note.repo_path)
        kept = {key: value for key, value in held.metadata.items() if key not in aside}
        return bool(held.text) and (kept, held.body.split()) == (note.metadata, note.body.split())

    def notes(self, within: Path = Path()) -> list[Note]:
        """Every note under `within`, as read back: each one there, then each one gone whose marginalia remain."""
        present = [self.load(repo_path) for repo_path in self.note_paths() if repo_path.path.is_relative_to(within)]
        return present + [self.load(RepoPath(path)) for path in self.gone(within)]

    def gone(self, within: Path = Path()) -> list[Path]:
        """Every note under `within` that is gone but whose marginalia remain, in order."""
        present = set(self.paths())
        return [path for path in self.annotated() if path.is_relative_to(within) and path not in present]

    def annotated(self) -> list[Path]:
        """The path of every note that has marginalia, in order, whether or not the note is still there."""
        return sorted(Path(path).relative_to(MARGINALIA) for path in self._ls(MARGINALIA.as_posix()))

    def into(self, path: Path) -> list[tuple[Note, Edge]]:
        """Every edge from another note that could mean `path`, with that note."""
        return [
            (note, edge)
            for note in self.notes()
            if note.repo_path.path != path
            for edge in note.edges
            if path in self.files.lands(edge)
        ]

    def check(self) -> list[BrokenLink]:
        """Every edge that lands on no node, or on no span it names."""
        return [found for note in self.notes() for edge in note.edges if (found := self.files.broken(edge))]

    def notes_named(self, spec: str) -> list[Path]:
        """The whole notes `spec` names; a span is refused, since marginalia speak for a whole note."""
        return self.files.resolve(_whole(spec))

    def tag(self, spec: str, tags: list[str]) -> list[Path]:
        """Label the notes `spec` names in their marginalia, committing as the user; returns the notes."""
        return self._retag(spec, lambda marginalia: marginalia.tagged(*tags), f"Tag {spec}: {', '.join(tags)}")

    def untag(self, spec: str, tags: list[str]) -> list[Path]:
        """Remove labels from the marginalia of the notes `spec` names, committing as the user; returns the notes."""
        return self._retag(spec, lambda marginalia: marginalia.untagged(*tags), f"Untag {spec}: {', '.join(tags)}")

    def link(self, from_spec: str, to_spec: str, why: str, on: date | None = None) -> Target:
        """Add an edge from a whole note to a note or a span in one, in its marginalia, committing as the user."""
        source, target = self.files.resolve_target(_whole(from_spec)).note, self.files.resolve_target(to_spec)
        today = date.today()  # noqa: DTZ011 - the user's local day, as the journal's
        marginalia = read_marginalia(self.root, source).linked(target, why, on or today)
        write_marginalia(self, replace(marginalia, ref=self.make_repo_path(source).ref))
        self.commit(f"Link {from_spec} to {target}", auto_index=False, as_user=True)
        return target

    def unlink(self, from_spec: str, to_spec: str) -> int:
        """Remove a note's edges to exactly `to_spec`'s target from its marginalia, committing as the user."""
        note = self.load(RepoPath(self.files.resolve_target(from_spec).note))
        try:
            target = str(self.files.resolve_target(to_spec))
        except UnresolvedNote as e:
            # An edge whose note is gone can't be named any more, so take it as the marginalia write it.
            target = to_spec.removeprefix("[[").removesuffix("]]")
            if target not in [said.link.target for said in note.said]:
                dead = [said.link.target for said in note.said if not self.files.lands(said)]
                hint = f"; a link whose note is gone is removed as written: {', '.join(dead)}" if dead else ""
                raise UnresolvedNote(f"{e}{hint}") from e
        marginalia, removed = note.unlinked(target)
        if not removed:
            raise ValueError(f"'{from_spec}' has no link to {target}")
        write_marginalia(self, marginalia)
        self.commit(f"Unlink {from_spec} from {target}", auto_index=False, as_user=True)
        return removed

    def _retag(self, spec: str, change: Callable[[Marginalia], Marginalia], message: str) -> list[Path]:
        notes = self.notes_named(spec)
        for note in notes:
            write_marginalia(self, replace(change(read_marginalia(self.root, note)), ref=self.make_repo_path(note).ref))
        self.commit(message, auto_index=False, as_user=True)
        return notes

    @cached_property
    def files(self) -> Files:
        """The files `paths` gives, indexed for landing edges and resolving specs; dropped on any write."""
        return Files(self.root, [*self.paths(), *(blob.path for blob in self.blobs())])

    def blobs(self, *names: str) -> list[Blob]:
        """Every archive stored, or those called any of `names`, in the order stored: committed, then not yet."""
        present, newest_first = (
            self._ls(BLOBS.as_posix()),
            _last_changed(self.root, self._head(), BLOBS.as_posix(), "%H"),
        )
        # A blob is never rewritten, so the commit that last changed it is the one that stored it.
        committed = [p for p in reversed(newest_first) if p in present]
        stored = [*committed, *sorted(present - set(committed))]
        return [Blob(Path(p)) for p in stored if not names or Path(p).name in names]

    def commit(
        self, message: str, auto_index: bool | None = None, *, as_user: bool = False, written: Iterable[str] = ()
    ) -> None:
        """Commit what this repo has saved, removed or stored since the last commit, and nothing else.

        Args:
            message: Commit message
            auto_index: Whether to index after committing (default: from config)
            as_user: Commit as the user's own git identity rather than the bot, for something they did themselves
            written: Paths written by other means, to commit with them
        """
        committed = _commit(self.root, self._pending | set(written), message, as_user=as_user)
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
            changed = self.uncommitted(".")
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


def _whole(spec: str) -> str:
    """`spec`, unless it names a span, which marginalia can't speak for: they belong to whole notes."""
    if "#" in spec:
        raise UnresolvedNote(f"'{spec}' names a span; marginalia belong to whole notes")
    return spec
