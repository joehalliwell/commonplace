"""Tests for the index and search commands."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from commonplace.__main__ import app
from commonplace._repo import Commonplace
from commonplace._types import Note

runner = CliRunner()


def test_index_rebuild(tmp_path):
    """Test the index command with --rebuild flag."""
    # Create a temporary commonplace repo
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add a test note
    note = Note(
        path=Path("test.md"),
        content="""# Test

Some content here.
""",
    )
    repo.save(note)

    # Mock the config
    mock_config = type("Config", (), {"root": repo_path, "user": "Test User"})()

    with patch("commonplace.__main__.get_config", return_value=mock_config):
        # Index first time
        result = runner.invoke(app, ["index"])
        assert result.exit_code == 0

        # Rebuild
        result = runner.invoke(app, ["index", "--rebuild"])
        assert result.exit_code == 0

    # Verify the index exists
    db_path = repo_path / ".commonplace" / "embeddings.db"
    assert db_path.exists()


def test_search(tmp_path):
    """Test the search command."""
    # Create a temporary commonplace repo
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add test notes with distinct content
    note1 = Note(
        path=Path("ml.md"),
        content="""# Machine Learning

## Introduction

Machine learning and neural networks are fascinating topics in AI.
""",
    )

    note2 = Note(
        path=Path("cooking.md"),
        content="""# Cooking

## Recipes

Baking bread requires flour, water, and yeast.
""",
    )

    repo.save(note1)
    repo.save(note2)
    repo.commit("Add test notes")

    # Mock the config
    mock_config = type("Config", (), {"root": repo_path, "user": "Test User"})()

    with patch("commonplace.__main__.get_config", return_value=mock_config):
        # Index the notes
        result = runner.invoke(app, ["index"])
        assert result.exit_code == 0

        # Search for ML-related content
        result = runner.invoke(app, ["search", "artificial intelligence"])
        assert result.exit_code == 0
        assert "ml.md" in result.stdout
        assert "Machine Learning" in result.stdout or "neural networks" in result.stdout


def test_search_no_index(tmp_path):
    """Test search command fails when index doesn't exist."""
    # Create a temporary commonplace repo without indexing
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)

    # Mock the config
    mock_config = type("Config", (), {"root": repo_path, "user": "Test User"})()

    with patch("commonplace.__main__.get_config", return_value=mock_config):
        result = runner.invoke(app, ["search", "test query"])
        assert result.exit_code == 1
        assert "Index not found" in result.stdout


def test_search_with_limit(tmp_path):
    """Test search command with --limit flag."""
    # Create a temporary commonplace repo
    repo_path = tmp_path / "commonplace"
    repo_path.mkdir()
    Commonplace.init(repo_path)
    repo = Commonplace.open(repo_path)

    # Add multiple notes
    for i in range(5):
        note = Note(
            path=Path(f"note{i}.md"),
            content=f"""# Note {i}

Content for note {i}.
""",
        )
        repo.save(note)

    # Mock the config
    mock_config = type("Config", (), {"root": repo_path, "user": "Test User"})()

    with patch("commonplace.__main__.get_config", return_value=mock_config):
        # Index
        result = runner.invoke(app, ["index"])
        assert result.exit_code == 0

        # Search with limit
        result = runner.invoke(app, ["search", "content", "--limit", "3"])
        assert result.exit_code == 0
        # Count the number of results (each starts with a number)
        result_count = sum(1 for line in result.stdout.split("\n") if line.startswith(("1.", "2.", "3.", "4.", "5.")))
        assert result_count <= 3
