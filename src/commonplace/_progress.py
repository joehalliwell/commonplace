import time
from collections.abc import Iterable, Iterator, Sized
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from rich.console import Group, RenderableType
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.text import Text

_live: Live | None = None
_live_renderables: list[RenderableType] = []


def start_live(renderable):
    global _live
    _live_renderables.append(renderable)
    if _live is None:
        _live = Live()
        _live.start(True)
    _live.update(Group(*_live_renderables))
    return renderable


def stop_live(renderable):
    global _live
    assert renderable in _live_renderables
    _live_renderables.remove(renderable)
    if not _live_renderables:
        # _live.update(Group(*_live_renderables))
        _live.refresh()
        _live.stop()
        _live = None
        return
    else:
        _live.update(Group(*_live_renderables))


class TaskFieldColumn(ProgressColumn):
    def __init__(self, field, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field = field

    def render(self, task):
        if task.fields.get(self.field) is None:
            return Text()
        # Assembled, not parsed: the value is arbitrary text, and `[/...]` in it would read as a closing tag.
        t = Text.assemble(f"{self.field}: ", (str(task.fields.get(self.field)), "bold blue"), overflow="ellipsis")
        t.no_wrap = True
        return t


@dataclass(frozen=True)
class Row:
    """One line of a display that outlives its work: how far a task has got, then how it ended."""

    progress: Progress
    task: TaskID

    def status(self, text: str) -> None:
        self.progress.update(self.task, status=text)

    def done(self) -> tuple[float, float | None]:
        """How many items `track` has passed through this row, of how many."""
        task = self.progress._tasks[self.task]
        return task.completed, task.total


#: The row `track` drives instead of a bar of its own, while one is set by `on`.
_row: ContextVar[Row | None] = ContextVar("row", default=None)


@contextmanager
def rows(names: Iterable[str]) -> Iterator[dict[str, Row]]:
    """A row per name, each waiting until its work starts, left on screen as they ended."""
    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=20),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("{task.fields[status]}"),
        TaskFieldColumn("item"),
    )
    table = {name: Row(progress, progress.add_task(name, total=None, start=False, status="waiting")) for name in names}
    start_live(progress)
    try:
        yield table
    finally:
        # The live display's last frame stays on screen, rows and all.
        stop_live(progress)


@contextmanager
def on(row: Row) -> Iterator[None]:
    """Send every `track` in the block, in this thread, to `row`."""
    token = _row.set(row)
    try:
        yield
    finally:
        _row.reset(token)


def _track_on(row: Row, iterable, describe):
    """`track`, driving `row` from nothing, and leaving it as it ends."""
    progress, task = row.progress, row.task
    progress.start_task(task)
    progress.reset(task, total=len(iterable) if isinstance(iterable, Sized) else None, status="")
    for item in iterable:
        progress.update(task, advance=1, item=describe(item))
        yield item
    # A generator's length is known once it's done.
    progress.update(task, total=progress._tasks[task].completed)


def track(iterable, name="", fields=dict, every=0.5, describe=lambda item: item):
    """Yield each item behind a progress bar showing `describe(item)`, reading a generator only as it's asked to."""
    if (row := _row.get()) is not None:
        yield from _track_on(row, iterable, describe)
        return
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(show_speed=True),
        TimeRemainingColumn(),  # SpinnerColumn(),
        TimeElapsedColumn(),
        TaskFieldColumn("item"),
        *(TaskFieldColumn(k) for k in fields()),
    )
    task = progress.add_task(name, total=len(iterable) if isinstance(iterable, Sized) else None)
    checkpoint_at = 0
    start_live(progress)
    # However the loop ends, a break, a raise or a stop, the bar comes down with it.
    try:
        for item in iterable:
            progress.update(task, advance=1, item=describe(item))
            if time.time() > checkpoint_at:
                progress.update(task, **fields())
                checkpoint_at = time.time() + every
            yield item
        progress.update(task, **fields())
    finally:
        stop_live(progress)
