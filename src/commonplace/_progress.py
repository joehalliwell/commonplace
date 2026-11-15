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
    Task,
    TaskID,
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

    def expect(self, more: int | None) -> None:
        """Start counting, with `more` items to come beyond those done, or an unknown number."""
        self._start()
        self.progress.update(self.task, total=None if more is None else self._task().completed + more)

    def advance(self, item: object = None) -> None:
        """Count one more item, showing it; a total it would outgrow grows with it."""
        self._start()
        task = self._task()
        total = task.total if task.total is None or task.completed < task.total else task.completed + 1
        self.progress.update(self.task, advance=1, total=total, item=item)

    def end(self) -> None:
        """Stop counting: what was counted is all there was."""
        self.progress.update(self.task, total=self._task().completed)

    def done(self) -> tuple[float, float | None]:
        """How many items this row has counted, of how many."""
        task = self._task()
        return task.completed, task.total

    def _start(self) -> None:
        if self._task().start_time is None:
            self.progress.start_task(self.task)
            self.progress.update(self.task, status="")

    def _task(self) -> Task:
        return next(task for task in self.progress.tasks if task.id == self.task)


#: The row that `track`, `tick` and `expect` count on, while `on` sets one.
_row: ContextVar[Row | None] = ContextVar("row", default=None)


@contextmanager
def rows(names: Iterable[str]) -> Iterator[dict[str, Row]]:
    """A row per name, each waiting until its work starts; the last frame stays on screen when the block ends."""
    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=20),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        TextColumn("{task.fields[status]}"),
        TaskFieldColumn("item"),
    )
    table = {name: Row(progress, progress.add_task(name, total=None, start=False, status="waiting")) for name in names}
    start_live(progress)
    try:
        yield table
    finally:
        stop_live(progress)


@contextmanager
def on(row: Row) -> Iterator[None]:
    """Count every `track`, `tick` and `expect` in the block, in this thread, on `row`."""
    token = _row.set(row)
    try:
        yield
    finally:
        _row.reset(token)


def tick(item: object = None) -> None:
    """Count one more item on the row `on` set, if any."""
    if (row := _row.get()) is not None:
        row.advance(item)


def expect(more: int | None) -> None:
    """Tell the row `on` set, if any, how many more items to expect."""
    if (row := _row.get()) is not None:
        row.expect(more)


def track(iterable, name=""):
    """Yield each item, counting it on the row `on` set or else on a row of its own; a generator is read as asked."""
    if (row := _row.get()) is not None:
        yield from _counted(row, iterable)
        return
    with rows([name]) as table:
        yield from _counted(table[name], iterable)


def _counted(row: Row, iterable):
    row.expect(len(iterable) if isinstance(iterable, Sized) else None)
    for item in iterable:
        row.advance(item)
        yield item
    row.end()
