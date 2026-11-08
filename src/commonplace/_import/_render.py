"""`doctor --render`: replay every stored chat archive, oldest capture first, and write what the replay ends on.

Later archives win, so each chat renders from the newest capture that holds it, and its `source_export`
names that capture. Undated archives (exports, Takeout, wire before v3) lose to dated ones, and go among
themselves in the order they were stored: never hash order, which is chance.
"""

from datetime import UTC, datetime
from pathlib import Path

from commonplace._import._commands import autodetect_importer, render_chats
from commonplace._import._placement import Placement
from commonplace._import._types import ChatImporter
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._repo import Commonplace
from commonplace._sources import importers
from commonplace._types import ChatSource, Note
from commonplace._wire import GZ, XZ, read_header

RENDER_MESSAGE = "Re-render chats from stored archives"

#: Subjects of the commits that render chats. Anything else last to touch one, `sync`'s auto-commit
#: included, carries a hand edit, which a re-render would overwrite.
_RENDERING = ("Import from ", "Fetch ", RENDER_MESSAGE)

_UNDATED = datetime.min.replace(tzinfo=UTC)


def render(repo: Commonplace, check: bool) -> tuple[list[str], list[str]]:
    """Re-render chats from the stored archives, leaving hand edits alone; returns actions and warnings."""
    archives = _in_capture_order(repo)
    final: dict[Path, Note] = {}
    winner: dict[Path, Path] = {}
    # One per tree, shared across archives, so a chat lands where the tree or an earlier archive put it.
    placements: dict[str, Placement] = {}
    for blob, importer in track(archives, "Replaying archives"):
        if importer.source.name not in placements:
            tree = importer.source.tree
            placements[importer.source.name] = Placement.of(repo, tree, importer.id_key)
        placement = placements[importer.source.name]
        rendered = {
            note.repo_path.path: note
            for note in render_chats(repo.root / blob, importer, repo.config.user, blob.as_posix(), placement)
        }
        final.update(rendered)
        winner.update(dict.fromkeys(rendered, blob))

    chats = ChatSource.ROOT.as_posix()
    subjects, dirty = repo.last_subjects(chats), repo.uncommitted(chats)
    writes: list[Note] = []
    hand_edited: list[str] = []
    for path, note in final.items():
        if repo.holds(note):
            continue
        if (repo.root / path).exists() and (
            path.as_posix() in dirty or not subjects.get(path.as_posix(), "").startswith(_RENDERING)
        ):
            hand_edited.append(path.as_posix())
            continue
        writes.append(note)

    superseded = len(archives) - len(set(winner.values()))
    if superseded:
        logger.info(f"   {superseded} of {len(archives)} archives superseded: later captures hold all they render")

    actions: list[str] = []
    if writes:
        new = sum(not (repo.root / note.repo_path.path).exists() for note in writes)
        actions.append(f"{'Would re-render' if check else 'Re-rendered'} {len(writes)} chats ({new} new)")
    if writes and not check:
        for note in writes:
            repo.save(note)
        repo.commit(RENDER_MESSAGE)

    warnings: list[str] = []
    if hand_edited:
        warnings.append(
            f"{len(hand_edited)} hand-edited chats left alone:\n" + "\n".join(f"  {p}" for p in hand_edited)
        )
    unrendered = [p for p in repo.paths() if p.is_relative_to(ChatSource.ROOT) and p.suffix == ".md" and p not in final]
    if unrendered:
        warnings.append(f"{len(unrendered)} chats no stored archive renders; left as they are")
    return actions, warnings


def _in_capture_order(repo: Commonplace) -> list[tuple[Path, ChatImporter]]:
    """Every stored archive a chat importer reads, oldest capture first, and of undated ones, the first stored."""
    archives: list[tuple[Path, ChatImporter]] = []
    for blob in repo.blobs():
        if importer := autodetect_importer(repo.root / blob.path, importers(ChatSource)):
            archives.append((blob.path, importer))

    def capture(archive: tuple[Path, ChatImporter]) -> tuple[bool, datetime]:
        blob = archive[0]
        fetched_at = read_header(repo.root / blob).fetched_at if blob.name.endswith((GZ, XZ)) else None
        return fetched_at is not None, fetched_at or _UNDATED

    return sorted(archives, key=capture)
