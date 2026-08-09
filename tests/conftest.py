import os
import tempfile
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest
from rich.console import Console

from commonplace._repo import Commonplace
from commonplace._search._types import Chunk
from commonplace._types import Note, RepoPath

# Dummy ref for tests that don't care about git history
TEST_REF = "0" * 40


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment with temporary directory for commonplace root."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set the environment variable for the test session
        os.environ["COMMONPLACE_ROOT"] = temp_dir
        yield temp_dir
        # Clean up after all tests
        if "COMMONPLACE_ROOT" in os.environ:
            del os.environ["COMMONPLACE_ROOT"]


@pytest.fixture
def make_note():
    """Helper to create a Note with RepoPath for testing."""

    def _make_note(path: str | Path, content: str, ref: str = TEST_REF) -> Note:
        repo_path = RepoPath(path=Path(path), ref=ref)
        return Note(repo_path=repo_path, content=content)

    return _make_note


@pytest.fixture
def make_chunk():
    """Helper to create a Chunk with RepoPath for testing."""

    def _make_chunk(path: str | Path, section: str, text: str, offset: int, ref: str = TEST_REF) -> Chunk:
        repo_path = RepoPath(path=Path(path), ref=ref)
        return Chunk(repo_path=repo_path, section=section, text=text, offset=offset)

    return _make_chunk


@pytest.fixture
def test_repo(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir(parents=True)
    Commonplace.init(repo_path)
    with closing(Commonplace.open(repo_path)) as repo:
        yield repo


@pytest.fixture
def test_index(test_repo):
    return test_repo.index


@pytest.fixture
def test_app(test_repo):
    from commonplace.__main__ import app

    def _run_app(args):
        return app.meta([f"--root={test_repo.root}", *args], result_action="return_int_as_exit_code_else_zero")

    return _run_app


@pytest.fixture
def sample_activity() -> Counter[date]:
    """
    A spread of activity that exercises every heatmap intensity level.

    Counts have to vary: thresholds are derived from the maximum, so uniform activity collapses the whole
    grid onto the top level and pins a degenerate rendering. Dates sit inside the 52 weeks before
    2024-01-20 so they show up in both the windowed and the all-time view.
    """
    return Counter(
        {
            date(2023, 8, 14): 1,
            date(2023, 11, 2): 3,
            date(2024, 1, 3): 5,
            date(2024, 1, 15): 9,
            date(2024, 1, 16): 2,
        }
    )


@pytest.fixture(params=[True, False], ids=["smart-terminal", "dumb-terminal"])
def any_terminal(request) -> Console:
    """
    A rich console in each rendering mode: styled (attached to a terminal) and plain (piped or headless).

    Rendering mode is otherwise inherited from the ambient terminal, so a test asserting on rendered output
    only ever exercises whichever mode the developer happens to be in. Every knob rich would take from the
    environment is pinned so the rendering is reproducible: the colour system (`auto` consults COLORTERM,
    and downgrades to None under TERM=dumb even when a terminal is forced), NO_COLOR, and both dimensions
    (TERM=dumb pins the size to 80x25 unless width *and* height are given).
    """
    styled: bool = request.param
    return Console(
        force_terminal=styled,
        color_system="truecolor" if styled else None,
        no_color=False,
        width=120,
        height=40,
    )


@pytest.fixture
def no_retry_sleep(monkeypatch):
    """Skip the exponential backoff sleep in fetcher retry tests."""
    monkeypatch.setattr("commonplace._fetch._helpers.time.sleep", lambda _: None)
