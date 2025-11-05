# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Commonplace is a personal knowledge management tool that imports AI conversation exports (Claude, Gemini, ChatGPT) and organizes them as searchable markdown files in a git repository. It supports semantic search via vector embeddings, full-text search, and hybrid search.

## Commands

```bash
# Testing
just test                              # Run all tests with coverage
uv run pytest tests/ -v                # Run tests directly
uv run pytest tests/test_import.py -v  # Run single test file
just update-snapshots                  # Update test snapshots

# Code quality
just format           # Format and lint
uv run mypy src/      # Type check

# Build & publish
uv build              # Build distribution
just publish          # Publish to PyPI

# Development
uv tool install .                           # Install locally
uv run commonplace import path/to/export.zip
uv run commonplace index
uv run commonplace search "query text"
```

## Architecture

**Repository** (`_repo.py`): `Commonplace` is the central object wrapping a git repo (pygit2) with cached properties: `config`, `cache`, `index`. Provides note management and indexing.

**Import** (`_import/`): Provider-specific importers (Claude/Gemini/ChatGPT) → `ActivityLog` → `MarkdownSerializer` → markdown files in `chats/{provider}/{year}/{month}/{date}-{title}.md`

**Search** (`_search/`): Protocol-based pipeline with `Chunker` (splits by sections) → `Embedder` (SentenceTransformers) → `VectorStore` (SQLite + FTS5). Supports semantic, full-text, and hybrid search. Index: `.commonplace/cache/index.db`

**Config** (`_config.py`): Pydantic-settings from env/`.env` with `COMMONPLACE_` prefix. Per-repo config at `.commonplace/config.toml`

**CLI** (`__main__.py`): Repo-centric with global `repo` object initialized in `launch()`. Top-level exception handler catches all command errors.

**Data flows:**

- Import: ZIP → Importer → ActivityLog → MarkdownSerializer → Note → git
- Index: Notes → Chunker → Chunks → Embedder → Embeddings → VectorStore
- Search: Query → Embedder → VectorStore → SearchHits

**Patterns:** Protocol interfaces, cached properties, top-level error handling, batch processing, incremental indexing, auto-commit on import

## Workflow

**All changes require tests.** New features need test cases, bug fixes need regression tests, refactoring maintains coverage.

**Test standards:**

- Descriptive names: `test_<feature>_<scenario>_<expected_result>`
- Positive and negative cases
- Use `conftest.py` fixtures
- Snapshot tests for complex output

**Code quality:**

- Python 3.12+, ruff (120 chars), mypy, type hints throughout
- Focused functions with docstrings for public APIs
- Update README.md for user-facing changes
- Pre-commit hooks run ruff automatically

**Change process:**

1. Propose with full context, explain rationale and trade-offs
1. Implement code
1. Write tests
1. Verify: `uv run pytest tests/ -v`
1. Format: `uv run ruff format .`
1. Update docs if needed

**Commits:** Imperative mood ("Add" not "Added"), concise, no AI credits/co-author tags
