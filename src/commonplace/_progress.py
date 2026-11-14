import time

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
        # Assembled, not parsed: the value is arbitrary text, and `[/...]` in it would read as a closing tag.
        t = Text.assemble(f"{self.field}: ", (str(task.fields.get(self.field)), "bold blue"), overflow="ellipsis")
        t.no_wrap = True
        return t


def track(iterable, name="", fields=dict, every=0.5):
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
