from rich.progress import Progress

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
