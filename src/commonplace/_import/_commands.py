"""Import entrypoint: find what claims a file, then import or mirror it."""

import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, is_zipfile

from commonplace import __version__
from commonplace._import._chatgpt import ChatGptImporter, ChatGptWireImporter
from commonplace._import._chatgpt_memory import ChatGptMemoryImporter
from commonplace._import._claude import ClaudeImporter
from commonplace._import._claude_code import ClaudeCodeImporter
from commonplace._import._claude_export import ClaudeExportImporter
from commonplace._import._claude_memory import ClaudeMemoryImporter
from commonplace._import._gemini import GeminiImporter
from commonplace._import._gemini_memory import GeminiMemoryImporter
from commonplace._import._gemini_takeout import GeminiTakeoutImporter
from commonplace._import._mirror import mirror_one
from commonplace._import._serializer import MarkdownSerializer
from commonplace._import._types import ChatImporter, MemoryImporter
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace
from commonplace._types import Metadata, Note, RepoPath
from commonplace._utils import slugify

#: Everything that can claim a file: chat importers accumulate, memory importers mirror live state.
IMPORTERS: list[ChatImporter | MemoryImporter] = [
    GeminiTakeoutImporter(),
    GeminiImporter(),
    GeminiMemoryImporter(),
    ClaudeExportImporter(),
    ClaudeImporter(),
    ClaudeMemoryImporter(),
    ClaudeCodeImporter(),
    ChatGptWireImporter(),
    ChatGptMemoryImporter(),
    ChatGptImporter(),
]


def import_(path: Path, repo: Commonplace, user: str, auto_index: bool | None = None):
    """Import an exported/local log or a directory of the same"""
    assert path.exists()
    if path.is_file():
        import_one(path, repo, user, auto_index=auto_index)
    else:
        logger.debug(f"Scanning '{path}' for export files")
        assert path.is_dir()
        paths_to_import = sorted(p for p in path.rglob("*") if p.is_file())
        for filepath in track(paths_to_import, "Importing files"):
            import_one(filepath, repo, user, auto_index=auto_index)


def landing_tree(source: str) -> Path:
    """Where `source` lands, which is also the pathspec its fetch cursor is read from."""
    for importer in IMPORTERS:
        if isinstance(importer, MemoryImporter) and importer.source == source:
            return importer.tree
    return Path("chats") / source


def autodetect_importer(path: Path) -> ChatImporter | MemoryImporter | None:
    assert path.is_file()
    for importer in IMPORTERS:
        try:
            if importer.can_import(path):
                logger.info(f"Using {importer.source} importer for {path}")
                return importer
        except:  # noqa
            logger.debug(f"{importer.source} cannot handle {path}", exc_info=True)
    logger.debug(f"No importer claimed '{path}'")
    return None


def extract_and_store(archive: Path, member: str, repo: Commonplace) -> RepoPath:
    """Extract one member from an archive and store it as a blob."""
    with tempfile.TemporaryDirectory() as tmp, ZipFile(archive) as zf:
        return repo.store_blob(Path(zf.extract(member, tmp)))


def import_one(path: Path, repo: Commonplace, user: str, auto_index: bool | None = None):
    """Import chats, overwriting any already there since commonplace owns them, or hand a mirrored source to `mirror_one`."""
    importer = autodetect_importer(path)
    if not importer:
        logger.debug(f"Skipping {path}")
        return
    if isinstance(importer, MemoryImporter):
        mirror_one(path, repo, importer, auto_index=auto_index)
        return
    # Store only the member an archive's importer reads, or the whole file for non-archives —
    # which includes a member already extracted from one, re-imported from the blob store.
    if importer.member and is_zipfile(path):
        blob = extract_and_store(path, importer.member, repo)
    else:
        blob = repo.store_blob(path)

    for rel_path, (metadata, body) in render_chats(path, importer, user, blob.path.as_posix()).items():
        repo.save(Note(repo_path=repo.make_repo_path(rel_path), body=body, metadata=metadata))
        logger.info(f"Stored log '{metadata['title']}' at '{rel_path}'")

    repo.commit(f"Import from '{path}' using '{importer.source}' importer", auto_index=auto_index)


def render_chats(path: Path, importer: ChatImporter, user: str, source_export: str) -> dict[Path, tuple[Metadata, str]]:
    """Each chat note the file at `path` renders to, by path, as frontmatter and body; writes nothing."""
    serializer = MarkdownSerializer(human=user, agent=importer.name)
    rendered: dict[Path, tuple[Metadata, str]] = {}
    used_paths: Counter[Path] = Counter()

    for log in importer.import_(path):
        rel_path = make_chat_path(source=log.source, date=log.created, title=log.title)
        used_paths.update([rel_path])
        count = used_paths[rel_path]
        if count > 1:
            rel_path = make_chat_path(source=log.source, date=log.created, title=f"{log.title}-{count}")

        # OKF keys first; `generated` is the importer's rendition, current as of the last event.
        log.metadata = {
            "type": "Chat",
            "title": log.title,
            **log.metadata,
            "generated": {
                "by": f"commonplace/{__version__}",
                "at": max((e.created for e in log.events), default=log.created).isoformat(timespec="seconds"),
            },
            "source": log.source,
            "source_export": source_export,
        }

        rendered[rel_path] = (log.metadata, serializer.serialize(log))

    return rendered


def make_chat_path(source: str, date: datetime, title: str | None) -> Path:
    """
    Generate the relative file path for storing an activity log.

    Args:
        source: The source system (e.g., 'claude', 'gemini')
        date: The creation date of the log
        title: Optional title to include in filename

    Returns:
        Path where the log should be stored
    """
    slug = ""
    if title:
        slug = "-" + slugify(title)
    return (
        landing_tree(source)
        / f"{date.year:02}"
        / f"{date.month:02}"
        / f"{date.year:02}-{date.month:02}-{date.day:02}{slug}.md"
    )
