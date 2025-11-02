import os
import tempfile
from contextlib import closing
from pathlib import Path

import pytest

from commonplace._repo import Commonplace
from commonplace._search._embedder import get_embedder
from commonplace._search._sqlite import SQLiteSearchIndex
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
def test_store(tmp_path):
    embedder = get_embedder()
    index_path = tmp_path / "cache" / "index.db"
    index_path.parent.mkdir(parents=True)
    with closing(SQLiteSearchIndex(index_path, embedder)) as store:
        yield store


@pytest.fixture
def test_repo(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir(parents=True)
    Commonplace.init(repo_path)
    with closing(Commonplace.open(repo_path)) as repo:
        yield repo
