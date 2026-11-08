"""Where a note lands: the readable path its date and title propose, unless it already holds one.

A note's path is its id in the graph, chosen readable because people browse the tree. The id a vendor gives it
only finds the path it first landed at, which it keeps, since marginalia and links hang off it; and a new note
whose proposed path is held takes the next free `-2`, `-3`.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from commonplace._repo import Commonplace


@dataclass
class Placement:
    """The paths a tree's notes hold, by id, and every path a new note may not take."""

    landed: dict[str, Path] = field(default_factory=dict)
    held: set[Path] = field(default_factory=set)

    @classmethod
    def of(cls, repo: "Commonplace", tree: Path, id_key: str | None) -> "Placement":
        """What `tree` holds now: each note by the id under `id_key`, and each gone note's marginalia."""
        landed: dict[str, Path] = {}
        if id_key is not None:
            for note in repo.notes(tree):
                if (note_id := note.metadata.get(id_key)) is not None:
                    landed[str(note_id)] = note.repo_path.path
        # Marginalia outlive their note: a new note at a gone note's path would silently inherit them.
        return cls(landed, set(landed.values()) | set(repo.gone(tree)))

    def place(self, proposed: Path, note_id: str | None) -> Path:
        """The path the note holds already, else `proposed` or the next free `-N` beside it, held from now on."""
        if note_id is not None and str(note_id) in self.landed:
            return self.landed[str(note_id)]
        path, n = proposed, 1
        while path in self.held:
            n += 1
            path = proposed.with_stem(f"{proposed.stem}-{n}")
        self.held.add(path)
        if note_id is not None:
            self.landed[str(note_id)] = path
        return path
