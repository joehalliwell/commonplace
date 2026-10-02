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
just update-snapshots                  # Update test snapshots (test_import.py, test_stats.py)

# Code quality
just format           # ruff check + format
uv run mypy src/      # Type check

# Build & publish
just publish          # Build and publish to PyPI

# Development
just install                                # Install the CLI editable; rerun after dependency changes. Main checkout only: in a worktree it repoints the CLI there
uv run commonplace import path/to/export.zip
uv run commonplace index
uv run commonplace search "query text"
```

## Architecture

**Repository** (`_repo.py`): `Commonplace` is the central object wrapping a git repo (pygit2) with cached properties: `config`, `cache`, `index`. Provides note management and indexing.

**Fetch** (`_fetch/`, `_wire.py`): Fetchers capture raw provider responses into a versioned wire archive and interpret nothing — the archive is the primitive artefact (MANIFESTO §3.2, §3.5), so any decision a fetcher makes is one no later reader can revisit. `_wire.py` owns the format for both sides; don't restate its rationale elsewhere. Each provider needs a Fetcher *and* a paired Importer, with the archive as the seam. Fetchers are brittle by nature (they track unofficial upstreams), so share freely between them — see `_fetch/_base.py`.

**Import** (`_import/`): Provider-specific importers (Claude/Gemini/ChatGPT) → `ActivityLog` → `MarkdownSerializer` → markdown files in `chats/{provider}/{year}/{month}/{date}-{title}.md`. All interpretation happens here. Those are `ChatImporter`s. Live upstream state (assistant memory) pairs its Fetcher with a `MemoryImporter` instead: same registry, but it yields a `Snapshot` that `_mirror.py` applies to `memory/{vendor}/`, pruning what the listing no longer names.

**Search** (`_search/`): Protocol-based pipeline with `Chunker` (splits by sections) → `Embedder` (SentenceTransformers) → `VectorStore` (SQLite + FTS5). Supports semantic, full-text, and hybrid search. Index: `.commonplace/cache/index.db`

**Config** (`_config.py`): Pydantic-settings; `Config.load(root)` overlays `COMMONPLACE_*` env over `.commonplace/config.toml` over the global `config.toml`.

**CLI** (`__main__.py`): Repo-centric with global `repo` object initialized in `launch()`. Top-level exception handler catches all command errors.

**Data flows:**

- Fetch: cookies → provider API → wire archive (gzipped JSONL) → Import
- Import (chat): ZIP or wire archive → ChatImporter → ActivityLog → MarkdownSerializer → Note → git
- Import (memory): wire archive → MemoryImporter → Snapshot → write + prune under `memory/{vendor}/` → git
- Index: Notes → Chunker → Chunks → Embedder → Embeddings → VectorStore
- Search: Query → Embedder → VectorStore → SearchHits

## Workflow

All changes require tests. Test names: `test_<feature>_<scenario>_<expected_result>`. Use `conftest.py` fixtures; snapshot tests for complex output.

Code standards: Python 3.12+, ruff at 120 chars, mypy, type hints throughout. Update README.md for user-facing changes.

Pre-commit hooks run ruff and mdformat. If mdformat reformats a file, re-stage and retry the commit.

Commits: imperative mood, concise. Keep the `Co-Authored-By` trailer — it records provenance, not credit. Commit each logical change separately in multi-step plans.

## Plugins

`plugins/commonplace-skills/` contains Claude Code skills and agents (version in `.claude-plugin/plugin.json`). These are **end-user tools** — they run inside a user's *commonplace repository* (their knowledge base), not in this Python codebase. Do not use them here.

**Skills:**

- `/synthesize [topic]` — gather and distil a topic from the commonplace
- `/resonate <slug1> <slug2> [...]` — surface interference patterns between synthesized topics
- `/rake` — surface unmade ideas, todos and projects; propose where to file them in `notes/`
- `/project <sketch>` — draft one project note, `notes/projects/{slug}.md`, or review and update an existing one

**Artefact paths** (no dated filenames — git is the versioning layer):

- `topics/{slug}.md` (the distillation), `topics/index.md`
- `topics/resonances/{sorted-slugs}.md`
- `.commonplace/skills/synthesize/{slug}.md` — a topic's gathering
- `notes/ideas.md`, `notes/todo.md`, `notes/projects/{slug}.md` — the user's own notes; `/rake` and `/project` only add what the user approves
- `.commonplace/skills/{skill}/` — skill-managed state nobody reads for its own sake (e.g. `rake/chaff.md`, items dropped in triage); never a source. Artefacts a person reads stay visible

**Conventions:**

- Heavy work (search, read, write) runs in a `general-purpose` subagent via the Task tool; the calling agent handles survey, review, and commit
- Artefacts update in place on incremental runs; prior state is recoverable via git
- Everything under `topics/` is an OKF v0.2 concept document (`type: Topic`). The repo root is the bundle; dot-directories are outside it. Staleness is `generated.by` (`<skill>/<plugin release>`) against the skill's newest Conventions entry, which is named by the release that introduced it
- Distillations and resonances carry a `## Revisions` section — one appended line per run, so the trajectory stays visible in-band rather than only in `git log`
- Gatherings quote from primitives only (`chats/`, `journal/`, `notes/`) and attribute every quote to a speaker; `topics/**` is derived and is never a source
