"""Import entrypoint: find what claims a file, then import or mirror it."""

import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, is_zipfile

from commonplace import __version__
from commonplace._config import BLOBS
from commonplace._import._mirror import mirror_one
from commonplace._import._placement import Placement
from commonplace._import._serializer import MarkdownSerializer
from commonplace._import._types import ChatImporter, MirrorImporter
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace
from commonplace._sources import importers
from commonplace._types import Blob, ChatSource, MirrorSource, Note
from commonplace._utils import slugify
from commonplace._wire import NewerWireVersion


def import_(path: Path, repo: Commonplace, user: str):
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
        import_one(path, repo, user)
    else:
        logger.debug(f"Scanning '{path}' for export files")
        paths_to_import = sorted(p for p in path.rglob("*") if p.is_file())
        for filepath in track(paths_to_import, "Importing files"):
            import_one(filepath, repo, user)


def autodetect_importer[I: (ChatImporter, MirrorImporter)](path: Path, importers: Sequence[I]) -> I | None:
    """The first of `importers` to claim the file at `path`."""
    assert path.is_file()
    for importer in importers:
        try:
            if importer.can_import(path):
                logger.info(f"Using {importer.source.name} importer for {path}")
                return importer
        except NewerWireVersion:
            # Ours, but from a newer commonplace: skipping it as not ours would lose it quietly.
            raise
        except Exception:  # noqa: BLE001 - probing an arbitrary file; any failure means "not ours"
            logger.debug(f"{importer.source.name} cannot handle {path}", exc_info=True)
    logger.debug(f"No importer claimed '{path}'")
    return None


def import_one(path: Path, repo: Commonplace, user: str, commit: bool = True) -> Blob | None:
    """Import chats, or hand a mirrored source to `mirror_one`; returns the blob stored, if any."""
    if mirror := autodetect_importer(path, importers(MirrorSource)):
        return mirror_one(path, repo, mirror)
    importer = autodetect_importer(path, importers(ChatSource))
    if not importer:
        logger.debug(f"Skipping {path}")
        return None
    # Store only the member an archive's importer reads, or the whole file for non-archives —
    # which includes a member already extracted from one, re-imported from the blob store.
    if importer.member and is_zipfile(path):
        with tempfile.TemporaryDirectory() as tmp, ZipFile(path) as zf:
            blob = repo.store_blob(Path(zf.extract(importer.member, tmp)))
    else:
        blob = repo.store_blob(path)

    placement = Placement.of(repo, importer.source.tree, importer.id_key)
    for note in render_chats(path, importer, user, blob.path.as_posix(), placement):
        repo.put(note)
        logger.info(f"Stored log '{note.metadata['title']}' at '{note.path}'")

    if commit:
        repo.commit(f"Import from '{path}' using '{importer.source.name}' importer")
    return blob


def render_chats(
    path: Path, importer: ChatImporter, user: str, source_export: str, placement: Placement | None = None
) -> list[Note]:
    """Each uncommitted chat note the file at `path` renders to, placed among what `placement` holds; writes nothing."""
    serializer = MarkdownSerializer(human=user, agent=importer.name)
    rendered: list[Note] = []
    placement = placement or Placement()

    for log in importer.import_(path):
        proposed = make_chat_path(importer.source.tree, date=log.created, title=log.title)
        rel_path = placement.place(proposed, log.metadata.get(importer.id_key) if importer.id_key else None)

        # `generated` is the importer's rendition, current as of the last event.
        metadata = {
            **log.metadata,
            "generated": {
                "by": f"commonplace/{__version__}",
                "at": max((e.created for e in log.events), default=log.created).isoformat(timespec="seconds"),
            },
            **importer.source.provenance(source_export),
        }
        rendered.append(Note.compose(rel_path, "Chat", log.title, serializer.serialize(log), metadata))

    return rendered


def make_chat_path(tree: Path, date: datetime, title: str | None) -> Path:
    """Where a chat lands: `{tree}/{yyyy}/{mm}/{date}-{slug}.md`, the slug from its title."""
    slug = ""
    if title:
        slug = "-" + slugify(title)
    return tree / f"{date.year:02}" / f"{date.month:02}" / f"{date.year:02}-{date.month:02}-{date.day:02}{slug}.md"
