"""The commonplace's git repository, and the one way anything reaches it.

Every git operation goes through `commonplace._git`, never a library. Every operation that writes commits what
it wrote: `put`, `remove` and `store_blob` record their paths, `commit` stages and commits exactly those, and
nothing else touches the index. Commits run the user's hooks. Neither `put` nor `remove` writes over a change
nothing committed, which nothing could recover, unless the writer read it first: `UncommittedChanges` names it
instead.
"""

import shutil
from collections.abc import Callable, Collection, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from functools import cached_property
from itertools import batched
from pathlib import Path
from typing import Literal

from commonplace import _git as git
from commonplace import _scaffold as scaffold
from commonplace._cache import INDEX_DB
from commonplace._config import BLOBS, MARGINALIA, Config
from commonplace._git import GitError
from commonplace._graph import FileSet, GraphStore, Half, fingerprint, own, said
from commonplace._links import BrokenLink, Files, Target
from commonplace._logging import logger
from commonplace._marginalia import marginalia_path, read_marginalia, write_marginalia
from commonplace._types import Blob, Note, Pathlike, node_id
from commonplace._utils import dump_frontmatter, load_frontmatter


def _own_half(read: Callable[[Path], Note], node: Path) -> Callable[[], Half]:
    """What `node`'s own file contributes, read when asked for."""
    return lambda: own(read(node))


def _said_half(root: Path, node: Path) -> Callable[[], Half]:
    """What `node`'s marginalia contribute, read when asked for, without reading the note itself."""
    return lambda: said(read_marginalia(root, node))


def _under(path: Path, folder: Path) -> bool:
    """Whether `path` is in `folder`, by its parts, which is cheaper than `is_relative_to` over a whole repository."""
    return path.parts[: len(folder.parts)] == folder.parts


class UncommittedChanges(ValueError):
    """Changes nothing has committed, which writing over them would lose for good."""

    def __init__(self, paths: Iterable[Path]):
        self.paths = sorted(paths)
        super().__init__(f"Uncommitted changes to {', '.join(map(str, self.paths))}: commit or discard them first")


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
            toplevel = Path(git.run_git(root, "rev-parse", "--show-toplevel").strip())
        except GitError as e:
            raise ValueError(f"{root} is not in a git repository") from e
        if toplevel != root.resolve():
            raise ValueError(f"{root} is not the root of its git repository, {toplevel}")
        try:
            git.run_git(toplevel, "rev-parse", "--verify", "-q", "HEAD")
        except GitError as e:
            raise ValueError("Repository has no commits yet") from e
        return Commonplace(root=toplevel)

    @cached_property
    def config(self) -> Config:
        return Config.load(self.root)

    def store_blob(self, source_path: Path) -> Blob:
        """Copy a file in as the blob it is, once, for the next commit."""
        blob = Blob.of(source_path)
        if not (self.root / blob.path).exists():
            (self.root / blob.path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, self.root / blob.path)
            self._wrote(blob.path)
        return blob

    @staticmethod
    def init(root: Path) -> "Commonplace":
        root.mkdir(parents=True, exist_ok=True)
        git.run_git(root, "init", "-q", "--initial-branch=main")
        scaffold.install(root)
        git.commit(root, set(scaffold.TEMPLATES), "Initial commit")
        return Commonplace.open(root)

    def content_ids(self) -> dict[Path, str]:
        """Each committed file, with git's id for its content at HEAD, uncommitted changes aside."""
        return {Path(path): content_id for path, content_id in git.content_ids(self.root, self.head()).items()}

    def head(self) -> str:
        """The commit checked out, which moves with every commit."""
        return self._git("rev-parse", "HEAD").strip()

    def uncommitted(self, pathspec: str) -> set[str]:
        """Paths under `pathspec` that differ from HEAD, untracked ones included."""
        tracked = git.z(self.root, "diff", "--name-only", "--no-renames", "HEAD", "--", pathspec)
        return {*tracked, *self._ls(pathspec, "--others")}

    def paths(self, within: Path = Path()) -> Iterator[Path]:
        """Every file under `within` that git would share, relative to the root, skipping dot-directories."""
        for path in sorted(map(Path, self._ls(within.as_posix()))):
            if not any(part.startswith(".") for part in path.parts[:-1]):
                yield path

    def _ls(self, pathspec: str, *which: str) -> set[str]:
        """The files under `pathspec` in the working tree that git would share, of `which` kinds, or tracked or not."""
        listed = git.z(
            self.root, "ls-files", *(which or ("--cached", "--others")), "--exclude-standard", "--", pathspec
        )
        return {path for path in listed if (self.root / path).exists()}

    def moved(self) -> dict[Path, Path]:
        """Where each path git ever saw renamed is now: a chain of moves to its end, a reused path by its latest."""
        # Newest first, so where a file moved to next is already known: `then` holds where what was at a path then is now.
        moved: dict[Path, Path] = {}
        then: dict[str, str] = {}
        for _, old, new in batched(git.z(self.root, "log", "-M", "--diff-filter=R", "--name-status", "--format="), 3):
            then[old] = then.get(new, new)
            moved.setdefault(Path(old), Path(then[old]))
        return moved

    def note_paths(self) -> Iterator[Path]:
        """Every note `paths` gives."""
        return (path for path in self.paths() if path.suffix == ".md")

    def get(self, path: Pathlike) -> Note:
        """The note at `path`, as the working tree has it, with its marginalia; one that's gone reads as empty."""
        path = node_id(path)
        return replace(self._read_note(path), marginalia=read_marginalia(self.root, path))

    def _read_note(self, path: Path) -> Note:
        """The note at `path` alone, without its marginalia."""
        logger.debug(f"Fetching note at {path}")
        file = self.root / path
        text = file.read_text(errors="replace") if path.suffix == ".md" and file.exists() else ""
        metadata, body = load_frontmatter(text)
        from commonplace._sources import source_holding, source_named

        # The source the note names, or failing that the one whose tree holds it.
        source = source_named(metadata.get("source")) or source_holding(path)
        return Note(path, body, metadata, text=text, source=source)

    def put(self, note: Note) -> None:
        """Write a note to the working tree for the next commit, over nothing uncommitted it didn't read."""
        self._check_unedited(note.path, note.text)
        abs_path = self.root / note.path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(dump_frontmatter(note.metadata, note.body))
        self._wrote(note.path)

    def remove(self, path: Path) -> None:
        """Delete a file from the working directory, for the next commit, unless it holds uncommitted changes."""
        self._check_unedited(path)
        (self.root / path).unlink()
        self._wrote(path)

    def ensure_unedited(self, within: Path) -> None:
        """Raise, naming them, if any paths under `within` have changes neither a commit nor this repo made."""
        edited = [Path(p) for p in self._edited - self._pending if Path(p).is_relative_to(within)]
        if edited:
            raise UncommittedChanges(edited)

    def _check_unedited(self, path: Path, seen: str = "") -> None:
        """Raise unless `path` is as HEAD has it, as this repo wrote it, or as its writer read it (`seen`)."""
        key = path.as_posix()
        if key in self._pending or key not in self._edited:
            return
        file = self.root / path
        if seen and file.exists() and file.read_text(errors="replace") == seen:
            return
        raise UncommittedChanges([path])

    @cached_property
    def _edited(self) -> set[str]:
        """Paths that differed from HEAD when this repo first looked, until its next commit."""
        return self.uncommitted(".")

    def _wrote(self, path: Path) -> None:
        """Hold `path` for the next commit, and drop the graph read before it changed."""
        self._pending.add(path.as_posix())
        self.__dict__.pop("files", None)

    # --- The repository as a graph: each file a node, its path its id, each link a note makes an edge ---

    def holds(self, note: Note, aside: Collection[str] = ()) -> bool:
        """Whether the working tree holds `note` already: its frontmatter, keys `aside` aside, and its words, since a
        formatting hook may rewrap or reindent what was written."""
        held = self.get(note.path)
        kept = {key: value for key, value in held.metadata.items() if key not in aside}
        return bool(held.text) and (kept, held.body.split()) == (note.metadata, note.body.split())

    def notes(self, within: Path = Path()) -> list[Note]:
        """Every note under `within`, as read back: each one there, then each one gone whose marginalia remain."""
        present = [self.get(path) for path in self.note_paths() if path.is_relative_to(within)]
        return present + [self.get(path) for path in self.gone(within)]

    def gone(self, within: Path = Path()) -> list[Path]:
        """Every note under `within` that is gone but whose marginalia remain, in order."""
        present = set(self.paths(within))
        return [path for path in self.annotated() if path.is_relative_to(within) and path not in present]

    def annotated(self) -> list[Path]:
        """The path of every note that has marginalia, in order, whether or not the note is still there."""
        return sorted(Path(path).relative_to(MARGINALIA) for path in self._ls(MARGINALIA.as_posix()))

    def check(self) -> list[BrokenLink]:
        """Every edge that lands on no one node, or on no span it names."""
        with self.graph() as graph:
            doubtful = graph.doubtful()
        return [found for edge in doubtful if (found := self.files.broken(edge))]

    @contextmanager
    def graph(self) -> Iterator[GraphStore]:
        """The graph, up to date with every file of every node, each read only if the store lacks its version."""
        # Every file git would share is in `ids`, so notes, blobs and marginalia need no listing of their own.
        ids = self.current_content_ids()
        paths = [path for path in ids if not any(part.startswith(".") for part in path.parts[:-1])]
        blobs = [path for path in ids if _under(path, BLOBS)]
        present = set(paths)
        nodes = [path for path in paths if path.suffix == ".md"]
        nodes += [
            note for path in ids if _under(path, MARGINALIA) and (note := path.relative_to(MARGINALIA)) not in present
        ]
        readers: dict[tuple[str, str], Callable[[], Half]] = {}
        for node in nodes:
            if (content_id := ids.get(node)) is not None:
                readers[(node.as_posix(), content_id)] = _own_half(self._read_note, node)
            if (content_id := ids.get(marginalia := marginalia_path(node))) is not None:
                readers[(marginalia.as_posix(), content_id)] = _said_half(self.root, node)
        with GraphStore(self.root / INDEX_DB) as graph:
            files = [*paths, *blobs]
            stamp = FileSet(fingerprint(files), lambda: Files(self.root, files))
            graph.sync(readers, lambda key: readers[key](), True, stamp)
            yield graph

    def current_content_ids(self) -> dict[Path, str]:
        """Each file in the working tree that git would share, with git's id for its content as it stands there."""
        changed = self.uncommitted(".")
        ids = {path: content_id for path, content_id in self.content_ids().items() if path.as_posix() not in changed}
        present = sorted(path for path in changed if (self.root / path).is_file())
        return ids | dict(zip(map(Path, present), git.hash_objects(self.root, present), strict=True))

    def add_link(self, note: Pathlike, target: Target, why: str = "", on: date | None = None) -> None:
        """Add an edge from `note` to `target`, resolved, a dated line in its marginalia, for the next commit."""
        on = on or date.today()  # noqa: DTZ011 - the user's local day, as the journal's
        write_marginalia(self, read_marginalia(self.root, node_id(note)).linked(target, why, on))

    def remove_link(self, note: Pathlike, target: Target | str) -> int:
        """Remove `note`'s edges to exactly `target` from its marginalia, for the next commit; how many went. A `Target`
        matches a link written by name or by path; a string, a link whose note is gone, as written."""
        written = {str(target), target.href} if isinstance(target, Target) else {target}
        marginalia, removed = self.get(node_id(note)).unlinked(written)
        if removed:
            write_marginalia(self, marginalia)
        return removed

    def label(self, note: Pathlike, *tags: str) -> None:
        """Add `tags` to `note`'s marginalia, for the next commit."""
        write_marginalia(self, read_marginalia(self.root, node_id(note)).tagged(*tags))

    def unlabel(self, note: Pathlike, *tags: str) -> None:
        """Remove `tags` from `note`'s marginalia, for the next commit."""
        write_marginalia(self, read_marginalia(self.root, node_id(note)).untagged(*tags))

    @cached_property
    def files(self) -> Files:
        """The files `paths` gives, indexed for landing edges and resolving specs; dropped on any write."""
        return Files(self.root, [*self.paths(), *map(Path, self._ls(BLOBS.as_posix()))])

    def blobs(self, *names: str, committed_only: bool = False) -> list[Blob]:
        """Every archive stored, or those called any of `names`, in the order stored: committed, then not yet."""
        present = self._ls(BLOBS.as_posix())
        # A blob is never rewritten, so the commit that last changed it is the one that stored it.
        committed = [p for p in reversed(git.last_changed(self.root, self.head(), ".", "%H")) if p in present]
        stored = committed if committed_only else [*committed, *sorted(present - set(committed))]
        return [Blob(Path(p)) for p in stored if not names or Path(p).name in names]

    def commit(self, message: str, *, as_user: bool = False, written: Iterable[str] = ()) -> None:
        """Commit what this repo has saved, removed or stored since the last commit, and nothing else.

        Args:
            message: Commit message
            as_user: Commit as the user's own git identity rather than the bot, for something they did themselves
            written: Paths written by other means, to commit with them
        """
        committed = git.commit(self.root, self._pending | set(written), message, as_user=as_user)
        self._pending.clear()
        self.__dict__.pop("_edited", None)
        logger.info(f"Committed changes with message: {message}" if committed else "No changes to commit")

    def sync(
        self,
        remote_name: str = "origin",
        branch: str | None = None,
        strategy: Literal["rebase", "merge"] = "rebase",
        auto_commit: bool = True,
    ) -> None:
        """Commit the user's own edits if `auto_commit`, then pull `branch` (default: the current one) and push it."""
        if remote_name not in self._git("remote").split():
            raise ValueError(f"Remote '{remote_name}' not found. Add remote first.")
        branch = branch or self._git("rev-parse", "--abbrev-ref", "HEAD").strip()
        logger.info(f"Syncing branch '{branch}' with '{remote_name}'")
        # The one commit of work commonplace didn't write: the user's own edits, whatever they are.
        if auto_commit and (changed := self.uncommitted(".")):
            git.commit(self.root, changed, f"Auto-commit before sync at {datetime.now(UTC).isoformat()}")
            self.__dict__.pop("_edited", None)
        try:
            self._git("pull", remote_name, branch, *(["--rebase"] if strategy == "rebase" else []))
        except GitError as e:
            if "couldn't find remote ref" not in str(e):
                raise
            logger.info(f"Remote branch {remote_name}/{branch} doesn't exist yet (first push)")
        self._git("push", remote_name, branch)
        logger.info(f"Synced with {remote_name}/{branch}")

    def _git(self, *args: str) -> str:
        return git.run_git(self.root, *args)
