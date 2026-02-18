# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Commonplace is a personal knowledge management tool that imports AI conversation exports (Claude, Gemini, ChatGPT) and organizes them as searchable markdown files in a git repository. It supports semantic search via vector embeddings, full-text search, and hybrid search.

`MANIFESTO.md` is the northstar for system design.

## Commands

```bash
# Testing
just test                              # Run tests with coverage
uv run pytest tests/test_import.py -v  # Run single test file
just update-snapshots                  # Update import snapshots (test_import.py only)

# Code quality
just format           # ruff check + format
uv run mypy src/      # Type check

# Build & publish
just publish          # Build and publish to PyPI

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

## Workflow

All changes require tests. Test names: `test_<feature>_<scenario>_<expected_result>`. Use `conftest.py` fixtures; snapshot tests for complex output.

Code standards: Python 3.12+, ruff at 120 chars, mypy, type hints throughout. Update README.md for user-facing changes.

Pre-commit hooks run ruff and mdformat. If mdformat reformats a file, re-stage and retry the commit.

Commits: imperative mood, concise, no AI credits. Commit each logical change separately in multi-step plans.

## Plugins

Claude Code skills and agents live in `plugins/commonplace-skills/` (current version: 0.8.0).

**Skills:**

- `/synthesize [topic]` — gather and distil a topic from the commonplace
- `/resonate <slug1> <slug2> [...]` — surface interference patterns between synthesized topics
- `/projects` — scan for candidate projects, update `projects/index.md`
- `/project <sketch>` — extract a project artefact from the commonplace

**Artefact paths** (no dated filenames — git is the versioning layer):

- `topics/{slug}/gathering.md`, `topics/{slug}/distillation.md`
- `topics/resonances/{sorted-slugs}.md`
- `projects/{slug}/project.md`, `projects/index.md`

**Conventions:**

- Heavy work (search, read, write) runs in a `general-purpose` subagent via the Task tool; the calling agent handles survey, review, and commit
- Artefacts update in place on incremental runs; prior state is recoverable via git
