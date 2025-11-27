import itertools as it
import time
from contextlib import contextmanager
from typing import Optional

from rich.console import Group, RenderableType
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.text import Text

_live: Optional[Live] = None
_live_renderables: list[RenderableType] = []


def start_live(renderable):
    global _live, _live_renderables
    _live_renderables.append(renderable)
    if _live is None:
        _live = Live()
        _live.start(True)
    _live.update(Group(*_live_renderables))
    return renderable


def stop_live(renderable):
    global _live, _live_renderables
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
        t = Text.from_markup(
            f"{self.field}: [bold blue]{task.fields.get(self.field)}[/]",
            overflow="ellipsis",
        )
        t.no_wrap = True
        return t


@contextmanager
def checkpoint(name="", every=0.5, fields=lambda: {}, quiet=False):
    if quiet:
        yield it.count()
        return

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(show_speed=True),
        TimeRemainingColumn(),  # SpinnerColumn(),
        TimeElapsedColumn(),
        *(TaskFieldColumn(k) for k in fields()),
    )
    start_live(progress)
    # progress.console.height = 1
    # progress.console.options.overflow = "ellipsis"
    task = progress.add_task(name, total=None, **fields())

    def generator():
        checkpoint_at = 0
        for step in it.count():
            progress.update(task, advance=1)
            if checkpoint_at < time.time():
                checkpoint_at = time.time() + every
                progress.update(task, **fields())
            yield step

    yield generator()
    progress.update(task, **fields())
    stop_live(progress)


def track(iterable, name="", fields=lambda: {}, every=0.5):
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
    iterable = list(iterable)
    task = progress.add_task(name, total=len(iterable))
    checkpoint_at = 0
    start_live(progress)
    for item in iterable:
        progress.update(task, advance=1, item=item)
        if time.time() > checkpoint_at:
            progress.update(task, **fields())
            checkpoint_at = time.time() + every
        yield item

    progress.update(task, **fields())
    stop_live(progress)


def demo(delay=0.04):
    with checkpoint() as steps:
        for x in track(range(5)):
            for y in track(range(10)):
                time.sleep(delay)

    step = 0
    with checkpoint(fields=lambda: {"steps": step + 1}) as steps:
        for step in it.islice(steps, 100):
            time.sleep(delay)


if __name__ == "__main__":
    demo()  # pragma: no cover
