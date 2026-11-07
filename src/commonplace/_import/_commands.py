"""Import entrypoint: find what claims a file, then import or mirror it."""

import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, is_zipfile

from commonplace import __version__
from commonplace._config import BLOBS
from commonplace._import._chatgpt import ChatGptImporter, ChatGptWireImporter
from commonplace._import._chatgpt_memory import ChatGptMemoryImporter
from commonplace._import._claude import ClaudeImporter
from commonplace._import._claude_code import ClaudeCodeImporter
from commonplace._import._claude_code_memory import ClaudeCodeMemoryImporter
from commonplace._import._claude_export import ClaudeExportImporter
from commonplace._import._claude_memory import ClaudeMemoryImporter
from commonplace._import._claude_tasks import ClaudeTasksImporter
from commonplace._import._gemini import GeminiImporter
from commonplace._import._gemini_memory import GeminiMemoryImporter
from commonplace._import._gemini_takeout import GeminiTakeoutImporter
from commonplace._import._keep import KeepImporter
from commonplace._import._mirror import mirror_one
from commonplace._import._placement import Placement
from commonplace._import._serializer import MarkdownSerializer
from commonplace._import._types import ChatImporter, MemoryImporter
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace
from commonplace._types import Note, RepoPath
from commonplace._utils import slugify
from commonplace._wire import NewerWireVersion

#: Importers that accumulate conversations under `chats/`, probed in order.
CHAT_IMPORTERS: list[ChatImporter] = [
    GeminiTakeoutImporter(),
    GeminiImporter(),
    ClaudeExportImporter(),
    ClaudeImporter(),
    ClaudeTasksImporter(),
    ClaudeCodeImporter(),
    ChatGptWireImporter(),
    ChatGptImporter(),
]

#: Importers that mirror live upstream state into a tree they own; an importer's kind is the list it is in.
MIRROR_IMPORTERS: list[MemoryImporter] = [
    GeminiMemoryImporter(),
    ClaudeMemoryImporter(),
    ClaudeCodeMemoryImporter(),
    ChatGptMemoryImporter(),
    KeepImporter(),
]


def import_(path: Path, repo: Commonplace, user: str, auto_index: bool | None = None):
    """Import an exported/local log or a directory of the same"""
    if not path.exists():
        raise FileNotFoundError(f"No such file or directory: '{path}'")
    # Re-importing stored archives lets whichever loads last win; `doctor --render` replays them in capture order.
    blobs, target = (repo.root / BLOBS).resolve(), path.resolve()
    if target.is_relative_to(blobs) or blobs.is_relative_to(target):
        raise ValueError(
            f"'{path}' is or holds this repo's blob store; re-render it with `commonplace doctor --render`"
        )
    if path.is_file():
        import_one(path, repo, user, auto_index=auto_index)
    else:
        logger.debug(f"Scanning '{path}' for export files")
        paths_to_import = sorted(p for p in path.rglob("*") if p.is_file())
        for filepath in track(paths_to_import, "Importing files"):
            import_one(filepath, repo, user, auto_index=auto_index)


def landing_tree(source: str) -> Path:
    """Where `source` lands, which is also the pathspec its fetch cursor is read from."""
    for importer in MIRROR_IMPORTERS:
        if importer.source == source:
            return importer.tree
    return Path("chats") / source


def autodetect_importer[I: (ChatImporter, MemoryImporter)](path: Path, importers: Sequence[I]) -> I | None:
    """The first of `importers` to claim the file at `path`."""
    assert path.is_file()
    for importer in importers:
        try:
            if importer.can_import(path):
                logger.info(f"Using {importer.source} importer for {path}")
                return importer
        except NewerWireVersion:
            # Ours, but from a newer commonplace: skipping it as not ours would lose it quietly.
            raise
        except Exception:  # noqa: BLE001 - probing an arbitrary file; any failure means "not ours"
            logger.debug(f"{importer.source} cannot handle {path}", exc_info=True)
    logger.debug(f"No importer claimed '{path}'")
    return None


def extract_and_store(archive: Path, member: str, repo: Commonplace) -> RepoPath:
    """Extract one member from an archive and store it as a blob."""
    with tempfile.TemporaryDirectory() as tmp, ZipFile(archive) as zf:
        return repo.store_blob(Path(zf.extract(member, tmp)))


def import_one(
    path: Path, repo: Commonplace, user: str, auto_index: bool | None = None, commit: bool = True
) -> RepoPath | None:
    """Import chats, or hand a mirrored source to `mirror_one`; returns the blob stored, if any."""
    if mirror := autodetect_importer(path, MIRROR_IMPORTERS):
        return mirror_one(path, repo, mirror, auto_index=auto_index)
    importer = autodetect_importer(path, CHAT_IMPORTERS)
    if not importer:
        logger.debug(f"Skipping {path}")
        return None
    # Store only the member an archive's importer reads, or the whole file for non-archives —
    # which includes a member already extracted from one, re-imported from the blob store.
    if importer.member and is_zipfile(path):
        blob = extract_and_store(path, importer.member, repo)
    else:
        blob = repo.store_blob(path)

    placement = Placement.of(repo.root, landing_tree(importer.source), importer.id_key)
    for note in render_chats(path, importer, user, blob.path.as_posix(), placement):
        repo.save(note)
        logger.info(f"Stored log '{note.metadata['title']}' at '{note.repo_path}'")

    if commit:
        repo.commit(f"Import from '{path}' using '{importer.source}' importer", auto_index=auto_index)
    return blob


def render_chats(
    path: Path, importer: ChatImporter, user: str, source_export: str, placement: Placement | None = None
) -> list[Note]:
    """Each uncommitted chat note the file at `path` renders to, placed among what `placement` holds; writes nothing."""
    serializer = MarkdownSerializer(human=user, agent=importer.name)
    rendered: list[Note] = []
    placement = placement or Placement()

    for log in importer.import_(path):
        proposed = make_chat_path(source=log.source, date=log.created, title=log.title)
        rel_path = placement.place(proposed, log.metadata.get(importer.id_key) if importer.id_key else None)

        # `generated` is the importer's rendition, current as of the last event.
        metadata = {
            **log.metadata,
            "generated": {
                "by": f"commonplace/{__version__}",
                "at": max((e.created for e in log.events), default=log.created).isoformat(timespec="seconds"),
            },
            "source": log.source,
            "source_export": source_export,
        }
        rendered.append(Note.compose(RepoPath(rel_path), "Chat", log.title, serializer.serialize(log), metadata))

    return rendered


def make_chat_path(source: str, date: datetime, title: str | None) -> Path:
    """Where a chat lands: `{tree}/{yyyy}/{mm}/{date}-{slug}.md`, the slug from its title."""
    slug = ""
    if title:
        slug = "-" + slugify(title)
    return (
        landing_tree(source)
        / f"{date.year:02}"
        / f"{date.month:02}"
        / f"{date.year:02}-{date.month:02}-{date.day:02}{slug}.md"
    )
