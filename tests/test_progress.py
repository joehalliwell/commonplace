from rich.progress import Progress

from commonplace import _progress
from commonplace._progress import TaskFieldColumn, on, rows, track


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


def test_track_inside_a_row_drives_that_row_and_shows_no_bar_of_its_own(bars):
    with rows(["claude"]) as table, on(table["claude"]):
        assert list(track(range(3), "Fetching claude")) == [0, 1, 2]
        assert table["claude"].done() == (3, 3)

    assert bars == ["claude"]


def test_a_row_starts_waiting_and_keeps_its_outcome_on_screen_when_done(capsys):
    with rows(["claude", "keep"]) as table:
        table["claude"].status("landed 2 archives")

    lines = capsys.readouterr().out.splitlines()
    assert any("claude" in line and "landed 2 archives" in line for line in lines)
    assert any("keep" in line and "waiting" in line for line in lines)


def test_track_on_a_row_counts_a_generator_out_once_it_ends():
    with rows(["keep"]) as table, on(table["keep"]):
        for _ in track(iter(range(3))):
            assert table["keep"].done()[1] is None

        assert table["keep"].done() == (3, 3)


def test_task_field_column_shows_nothing_for_a_field_not_yet_set():
    progress = Progress()
    task_id = progress.add_task("")

    assert TaskFieldColumn("item").render(progress.tasks[task_id]).plain == ""


def test_a_row_that_outgrows_its_total_grows_it():
    """Claude's scheduled tasks page each run's events, so a total expected per run is only a floor."""
    with rows(["claude-tasks"]) as table:
        table["claude-tasks"].expect(1)
        table["claude-tasks"].advance()
        table["claude-tasks"].advance()

        assert table["claude-tasks"].done() == (2, 2)
