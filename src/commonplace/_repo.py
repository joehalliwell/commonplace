import os
import shelve
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from pygit2 import init_repository, Signature
from pygit2.enums import FileStatus
from pygit2.repository import Repository

from commonplace import logger
from commonplace._types import Note, Pathlike


@dataclass
class Commonplace:
    """
    Wraps a git repo
    """

    git: Repository
    cache: shelve.Shelf

    @staticmethod
    def open(root: Path) -> "Commonplace":
        root = root.absolute()
        logger.info(f"Opening commonplace repository at {root}")
        git = Repository(root.as_posix())
        cache = shelve.open(root / ".commonplace" / "cache" / "notes")
        return Commonplace(git=git, cache=cache)

    @staticmethod
    def init(root: Path):
        init_repository(root, bare=False)
        os.makedirs(root / ".commonplace", exist_ok=True)
        os.makedirs(root / ".commonplace" / "cache", exist_ok=True)

    @property
    def root(self) -> Path:
        """Get the root path of the repository."""
        return Path(self.git.workdir)

    def notes(self) -> Iterator[Note]:
        """Get an iterator over all notes in the repository."""
        for root, dirs, files in os.walk(self.git.workdir):
            for f in files:
                path = Path(root) / f
                if self.git.path_is_ignored(path.as_posix()):
                    continue
                if path.suffix != ".md":
                    continue
                try:
                    yield self._get_note(path)
                except Exception:
                    logger.warning(f"Can't parse {path}")

    def _get_note(self, path: Pathlike) -> Note:
        """
        Low-level method to fetch a note from the repository.

        Args:
            path (Pathlike): Note path relative to the repository root.

        Returns:
            Note: Note object containing the content and metadata.
        """
        logger.debug(f"Fetching note at {path}")
        path = self._rel_path(path)
        flags = self.git.status_file(path.as_posix())
        ref = self.git.head.target
        if flags == FileStatus.CURRENT:  # Hence cacheable
            key = f"{path}@{ref}"
            if key not in self.cache:
                logger.info(f"No cache for {path}")
                note = self._read_note(path)
                self.cache[key] = note
            else:
                logger.debug(f"Cache hit for {path}")
            return self.cache[key]
        else:
            return self._read_note(path)

    def _read_note(self, path: Pathlike) -> Note:
        logger.debug(f"Reading {path}")
        with open(Path(self.git.workdir) / path) as fd:
            content = fd.read()
            return Note(path=path, content=content)

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

    def _abs_path(self, path: Pathlike) -> Path:
        """
        Returns an absolute path to the note within the repository.

        Args:
            path (Pathlike): Path to the note, can be absolute or relative.

        """
        path = self._rel_path(path)
        return Path(self.git.workdir) / path

    def save(self, note: Note) -> None:
        """Save a note and add it to git staging"""
        abs_path = self._abs_path(note.path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as fd:
            fd.write(note.content)
        self.git.index.add(self._rel_path(note.path))

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


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    root = "/home/joe/work/commonplace-private"
    repo = Commonplace.open(Path(root))
    count = 0
    for note in repo.notes():
        count += 1
    logger.info(f"Read {count} notes")
