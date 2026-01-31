"""Chat importers"""

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from commonplace._import._chatgpt import ChatGptImporter
from commonplace._import._claude import ClaudeImporter
from commonplace._import._claude_code import ClaudeCodeImporter
from commonplace._import._gemini import GeminiImporter
from commonplace._import._serializer import MarkdownSerializer
from commonplace._import._types import Importer
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace
from commonplace._types import Note
from commonplace._utils import merge_frontmatter, slugify

IMPORTERS: list[Importer] = [
    GeminiImporter(),
    ClaudeImporter(),
    ClaudeCodeImporter(),
    ChatGptImporter(),
]


def import_(path: Path, repo: Commonplace, user: str, prefix="chats", auto_index: bool | None = None):
    """Import an exported/local log or a directory of the same"""
    assert path.exists()
    if path.is_file():
        import_one(path, repo, user, prefix=prefix, auto_index=auto_index)
    else:
        logger.debug("Scanning '{path}' for export files")
        assert path.is_dir()
        paths_to_import = sorted(p for p in path.rglob("*") if p.is_file())
        for filepath in track(paths_to_import, "Importing files"):
            import_one(filepath, repo, user, prefix=prefix, auto_index=auto_index)


def autodetect_importer(path: Path) -> Optional[Importer]:
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


def import_one(path: Path, repo: Commonplace, user: str, prefix="chats", auto_index: bool | None = None):
    """
    Import chats from a supported provider into the repository.

    If a conversation already exists at the target path, metadata will be merged:
    - Fields provided by the importer will be updated with new values
    - User-added fields (not in importer metadata) will be preserved
    """
    importer = autodetect_importer(path)
    if not importer:
        logger.debug(f"Skipping {path}")
        return
    serializer = MarkdownSerializer(human=user, assistant=importer.source.title())
    blob_path = repo.store_blob(path)

    used_paths: Counter[Path] = Counter()

    for log in importer.import_(path):
        rel_path = make_chat_path(source=log.source, date=log.created, title=log.title)
        used_paths.update([rel_path])
        count = used_paths[rel_path]
        if count > 1:
            rel_path = make_chat_path(source=log.source, date=log.created, title=f"{log.title}-{count}")

        log.metadata["source"] = log.source
        log.metadata["source_export"] = blob_path.path.as_posix()

        # Check if file already exists and merge metadata if so
        abs_path = repo.root / rel_path
        if abs_path.exists():
            existing_content = abs_path.read_text()
            merged_metadata = merge_frontmatter(existing_content, log.metadata)
            log.metadata = merged_metadata
            logger.debug(f"Merged metadata for existing file '{rel_path}'")

        # Create RepoPath for the new note (will get proper ref after commit)
        repo_path = repo.make_repo_path(rel_path)

        note = Note(
            repo_path=repo_path,
            content=serializer.serialize(log),
        )
        repo.save(note)
        logger.info(f"Stored log '{log.title}' at '{rel_path}'")

    repo.commit(f"Import from '{path}' using '{importer.source}' importer", auto_index=auto_index)


def make_chat_path(source: str, date: datetime, title: Optional[str], prefix="chats") -> Path:
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
        Path(prefix)
        / source
        / f"{date.year:02}"
        / f"{date.month:02}"
        / f"{date.year:02}-{date.month:02}-{date.day:02}{slug}.md"
    )
