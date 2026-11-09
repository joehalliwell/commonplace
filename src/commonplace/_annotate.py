"""`tag`, `untag`, `link` and `unlink`: what a person names, resolved to notes, then written to their marginalia.

The repository's writes are `Commonplace.label`, `unlabel`, `add_link` and `remove_link`, which take nodes. Here a spec
becomes the notes it names, a span is refused where marginalia speak for a whole note, and each command commits as
the person, since they did it themselves.
"""

from datetime import date
from pathlib import Path

from commonplace._links import Target, UnresolvedNote
from commonplace._repo import Commonplace


def tag(repo: Commonplace, spec: str, tags: list[str]) -> list[Path]:
    """Label the notes `spec` names; returns the notes."""
    notes = repo.files.resolve(_whole(spec))
    for note in notes:
        repo.label(note, *tags)
    repo.commit(f"Tag {spec}: {', '.join(tags)}", as_user=True)
    return notes


def untag(repo: Commonplace, spec: str, tags: list[str]) -> list[Path]:
    """Remove labels from the notes `spec` names; returns the notes."""
    notes = repo.files.resolve(_whole(spec))
    for note in notes:
        repo.unlabel(note, *tags)
    repo.commit(f"Untag {spec}: {', '.join(tags)}", as_user=True)
    return notes


def link(repo: Commonplace, from_spec: str, to_spec: str, why: str, on: date | None = None) -> Target:
    """Link a whole note to a note or a span in one, written as the target resolves so it means the same later."""
    source, target = repo.files.resolve_target(_whole(from_spec)).note, repo.files.resolve_target(to_spec)
    repo.add_link(source, str(target), why, on)
    repo.commit(f"Link {from_spec} to {target}", as_user=True)
    return target


def unlink(repo: Commonplace, from_spec: str, to_spec: str) -> int:
    """Remove a note's links to exactly `to_spec`'s target; how many went."""
    source = repo.files.resolve_target(from_spec).note
    target = _as_written(repo, source, to_spec)
    if not (removed := repo.remove_link(source, target)):
        raise ValueError(f"'{from_spec}' has no link to {target}")
    repo.commit(f"Unlink {from_spec} from {target}", as_user=True)
    return removed


def _as_written(repo: Commonplace, source: Path, spec: str) -> str:
    """The target `spec` names, or for a link whose note is gone and can't be named any more, `spec` as written."""
    try:
        return str(repo.files.resolve_target(spec))
    except UnresolvedNote as e:
        target, said = spec.removeprefix("[[").removesuffix("]]"), repo.get(source).said
        if target not in [edge.link.target for edge in said]:
            dead = [edge.link.target for edge in map(repo.files.landing, said) if not isinstance(edge.to, Path)]
            hint = f"; a link whose note is gone is removed as written: {', '.join(dead)}" if dead else ""
            raise UnresolvedNote(f"{e}{hint}") from e
        return target


def _whole(spec: str) -> str:
    """`spec`, unless it names a span, which marginalia can't speak for: they belong to whole notes."""
    if "#" in spec:
        raise UnresolvedNote(f"'{spec}' names a span; marginalia belong to whole notes")
    return spec
