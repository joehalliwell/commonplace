from rich.progress import Progress

from commonplace import _progress
from commonplace._progress import TaskFieldColumn, track


def test_track():
    for i in track(range(5)):
        print(i)


def test_nested_track():
    for i in track(range(5)):
        for j in track(range(5)):
            print(i, j)


def test_task_field_column_shows_markup_like_text_verbatim():
    progress = Progress()
    task_id = progress.add_task("", item="[/posts/flat-apis/] and [bold]")

    text = TaskFieldColumn("item").render(progress.tasks[task_id])

    assert text.plain == "item: [/posts/flat-apis/] and [bold]"


def test_track_reads_a_generator_one_item_at_a_time():
    """Keep asks for each page by the version the last one reached, so nothing may be read ahead."""
    read: list[int] = []

    def pages():
        for page in range(3):
            read.append(page)
            yield page

    assert [(page, list(read)) for page in track(pages())] == [(0, [0]), (1, [0, 1]), (2, [0, 1, 2])]


def test_track_left_early_takes_its_bar_down():
    """A fetch that stops at a resync, or raises, must not leave its bar on screen for the rest of the run."""
    for _ in track(range(5)):
        break

    assert _progress._live_renderables == [] and _progress._live is None
