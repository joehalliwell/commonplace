"""`doctor --render`: replay every stored chat archive, oldest capture first, and write what the replay ends on.

Later archives win, so each chat renders from the newest capture that holds it, and its `source_export`
names that capture. Undated archives (exports, Takeout, wire before v3) lose to dated ones, and go among
themselves in the order they were stored: never hash order, which is chance.
"""

from datetime import UTC, datetime
from pathlib import Path

from commonplace._import._commands import autodetect_importer, render_chats
from commonplace._import._types import ChatImporter
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace
from commonplace._types import Metadata, Note
from commonplace._utils import dump_frontmatter
from commonplace._wire import read_header

RENDER_MESSAGE = "Re-render chats from stored archives"

#: Subjects of the commits that render chats. Anything else last to touch one, `sync`'s auto-commit
#: included, carries a hand edit, which a re-render would overwrite.
_RENDERING = ("Import from ", RENDER_MESSAGE)

_BLOBS = ".commonplace/blobs"
_CHATS = "chats"
_UNDATED = datetime.min.replace(tzinfo=UTC)


def render(repo: Commonplace, check: bool) -> tuple[list[str], list[str]]:
    """Re-render chats from the stored archives, leaving hand edits alone; returns actions and warnings."""
    archives = _in_capture_order(repo)
    final: dict[Path, tuple[Metadata, str]] = {}
    winner: dict[Path, Path] = {}
    for blob, importer in track(archives, "Replaying archives"):
        rendered = render_chats(repo.root / blob, importer, repo.config.user, blob.as_posix())
        final.update(rendered)
        winner.update(dict.fromkeys(rendered, blob))

    subjects, dirty = repo.last_subjects(_CHATS), repo.uncommitted(_CHATS)
    writes: dict[Path, tuple[Metadata, str]] = {}
    hand_edited: list[str] = []
    for path, (metadata, body) in final.items():
        target = repo.root / path
        if target.exists() and target.read_text() == dump_frontmatter(metadata, body):
            continue
        if target.exists() and (
            path.as_posix() in dirty or not subjects.get(path.as_posix(), "").startswith(_RENDERING)
        ):
            hand_edited.append(path.as_posix())
            continue
        writes[path] = (metadata, body)

    superseded = len(archives) - len(set(winner.values()))
    if superseded:
        logger.info(f"   {superseded} of {len(archives)} archives superseded: later captures hold all they render")

    actions: list[str] = []
    if writes:
        new = sum(not (repo.root / path).exists() for path in writes)
        actions.append(f"{'Would re-render' if check else 'Re-rendered'} {len(writes)} chats ({new} new)")
    if writes and not check:
        for path, (metadata, body) in writes.items():
            repo.save(Note(repo_path=repo.make_repo_path(path), body=body, metadata=metadata))
        repo.commit(RENDER_MESSAGE)

    warnings: list[str] = []
    if hand_edited:
        warnings.append(
            f"{len(hand_edited)} hand-edited chats left alone:\n" + "\n".join(f"  {p}" for p in hand_edited)
        )
    unrendered = [p for p in (repo.root / _CHATS).glob("**/*.md") if p.relative_to(repo.root) not in final]
    if unrendered:
        warnings.append(f"{len(unrendered)} chats no stored archive renders; left as they are")
    return actions, warnings


def _in_capture_order(repo: Commonplace) -> list[tuple[Path, ChatImporter]]:
    """Every stored archive a chat importer reads, oldest capture first."""
    stored = {path: i for i, path in enumerate(repo.first_added(_BLOBS))}
    archives: list[tuple[Path, ChatImporter]] = []
    for path in sorted((repo.root / _BLOBS).glob("*/*")):
        if isinstance(importer := autodetect_importer(path), ChatImporter):
            archives.append((path.relative_to(repo.root), importer))

    def capture(archive: tuple[Path, ChatImporter]) -> tuple[bool, datetime, int]:
        blob = archive[0]
        fetched_at = read_header(repo.root / blob).fetched_at if blob.name.endswith(".jsonl.gz") else None
        # An uncommitted blob was stored last.
        return fetched_at is not None, fetched_at or _UNDATED, stored.get(blob.as_posix(), len(stored))

    return sorted(archives, key=capture)
