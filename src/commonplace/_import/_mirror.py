"""Apply a [[commonplace._import._types.MirrorImporter]]'s snapshot to the repository.

A mirror, not an import: the upstream state is live, rewritten and deleted in
place, so the tree holds what the latest capture listed and git holds the
trajectory. Everything here is the same for every vendor.
"""

from dataclasses import replace
from pathlib import Path

from commonplace._import._placement import Placement
from commonplace._import._types import MirrorImporter
from commonplace._logging import logger
from commonplace._repo import Commonplace
from commonplace._types import Note, RepoPath, Source
from commonplace._wire import archive_names, read_header


def mirror_one(
    path: Path, repo: Commonplace, importer: MirrorImporter, auto_index: bool | None = None
) -> RepoPath | None:
    """Land the files the capture read and prune the paths its listing no longer names; returns the blob stored."""
    tree = importer.source.tree
    fetched_at = read_header(path).fetched_at
    landed_at = repo.last_commit_time(f"{tree.as_posix()}/")
    if fetched_at and landed_at and fetched_at < landed_at:
        logger.error(f"Not mirroring '{path}': captured {fetched_at}, but '{tree}' was last changed {landed_at}")
        return None

    # Captures of this source already landed, for an importer whose captures are changes on earlier ones.
    earlier = [repo.root / blob.path for blob in repo.blobs(*archive_names(importer.source.name))]
    snapshot = importer.snapshot(path, earlier=earlier)
    if importer.id_key is not None:
        snapshot = replace(snapshot, notes=_placed(repo, tree, importer.id_key, snapshot.notes))
    # Paths come from upstream, and a mirror owns its tree and nothing else.
    for note in snapshot.notes:
        if not note.repo_path.path.is_relative_to(tree) or note.repo_path.path == tree:
            raise ValueError(f"'{path}' names '{note.repo_path}', outside '{tree}'")
    # A re-read is a new blob, so rewriting what is already there would change only its provenance.
    notes = [note for note in snapshot.notes if not _landed(repo, importer.source, note)]

    stale: list[Path] = []
    if snapshot.unread is None:
        # Without the complete listing, absence means nothing.
        logger.warning(f"'{path}' has no listing; nothing pruned")
    else:
        kept = snapshot.unread | {note.repo_path.path for note in snapshot.notes}
        stale = [p for p in repo.paths() if p.is_relative_to(tree) and p not in kept]

    # Decided before the blob is stored, so a capture that changes nothing leaves no trace.
    if not notes and not stale:
        logger.info(f"'{tree}' already matches '{path}'")
        return None

    blob = repo.store_blob(path)
    provenance = importer.source.provenance(blob.path.as_posix())
    for note in notes:
        repo.save(replace(note, metadata=note.metadata | provenance))
        logger.info(f"Mirrored '{note.repo_path}'")
    for target in stale:
        repo.remove(target)
        logger.info(f"Pruned '{target}'")

    repo.commit(f"Mirror {importer.source.name}: {blob.path.as_posix()}", auto_index=auto_index)
    return blob


def _placed(repo: Commonplace, tree: Path, id_key: str, notes: list[Note]) -> list[Note]:
    """Each note at the path it first landed at, found by its id; a new note, in order, clear of every path held."""
    placement = Placement.of(repo, tree, id_key)
    return [
        replace(
            note, repo_path=replace(note.repo_path, path=placement.place(note.repo_path.path, note.metadata[id_key]))
        )
        for note in notes
    ]


def _landed(repo: Commonplace, source: Source, note: Note) -> bool:
    """Whether the working tree already holds this note, whichever capture it was landed from."""
    held = repo.load(note.repo_path)
    landed = note.metadata | source.provenance(held.metadata.get("source_export", ""))
    # Whitespace aside, since a formatting hook may rewrap what was landed.
    return bool(held.text) and (held.metadata, held.body.split()) == (landed, note.body.split())
