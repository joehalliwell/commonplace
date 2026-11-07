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
just update-snapshots                  # Update test snapshots (test_import.py, test_memory.py, test_stats.py)

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

**Repository** (`_repo.py`): `Commonplace` is the central object wrapping a git repo with cached properties: `config`, `cache`, `index`. Provides note management and indexing. Every git operation goes through the git CLI via `_run_git()`, never a library: re-implementing the porcelain cost us a silent revert (#102). Every operation that writes commits what it wrote: methods record paths, `commit()` stages and commits exactly those, and nothing else touches the index. Commits run the user's hooks.

**Fetch** (`_fetch/`, `_wire.py`): Fetchers capture raw vendor responses into a versioned wire archive and interpret nothing — the archive is the primitive artefact (MANIFESTO §3.2, §3.5), so any decision a fetcher makes is one no later reader can revisit. So a fetcher errs on the side of caution: it captures all of the user's material it can reach and leaves every judgement of what's worth reading to its importer, excluding only what isn't the user's (account and auth state). `_wire.py` owns the format for both sides; don't restate its rationale elsewhere. Each source needs a Fetcher *and* a paired Importer, with the archive as the seam. Fetchers are brittle by nature (they track unofficial upstreams), so share freely between them — see `_fetch/_base.py`.

**Import** (`_import/`): Per-agent importers (Claude/Claude Code/Gemini/ChatGPT) → `ActivityLog` → `MarkdownSerializer` → markdown files in `chats/{agent}/{year}/{month}/{date}-{title}.md`. All interpretation happens here. Those are `ChatImporter`s. Live upstream state (agent memory) pairs its Fetcher with a `MemoryImporter` instead: same registry, but it yields a `Snapshot` that `_mirror.py` applies to `memory/{agent}/`, pruning what the listing no longer names.

**Paths are for people** (MANIFESTO §4.2): a commonplace is a graph projected onto a tree a person browses like an org-mode outline, so readability is the point of a path. Name files by date and title, never by an id. An id may only *find* the path a note already holds, and a clash takes the next free `-2`, `-3`. A note keeps its first path through retitles, since marginalia and links are keyed by path. `_import/_placement.py` is the one place this happens, for chats and mirrors alike.

**Search** (`_search/`): Protocol-based pipeline with `Chunker` (splits by sections) → `Embedder` (SentenceTransformers) → `VectorStore` (SQLite + FTS5). Supports semantic, full-text, and hybrid search. Index: `.commonplace/cache/index.db`

**Config** (`_config.py`): Pydantic-settings; `Config.load(root)` overlays `COMMONPLACE_*` env over `.commonplace/config.toml` over the global `config.toml`.

**CLI** (`__main__.py`): Repo-centric with global `repo` object initialized in `launch()`. Top-level exception handler catches all command errors.

**Data flows:**

- Fetch: cookies → vendor API → wire archive (xz-compressed JSONL; gzip before 0.8.0) → Import; Claude Code's fetcher reads local files instead (`~/.claude/projects/`)
- Import (chat): ZIP or wire archive → ChatImporter → ActivityLog → MarkdownSerializer → Note → git
- Import (memory): wire archive → MemoryImporter → Snapshot → write + prune under `memory/{agent}/` → git
- Index: Notes → Chunker → Chunks → Embedder → Embeddings → VectorStore
- Search: Query → Embedder → VectorStore → SearchHits

## Workflow

Priorities: work that preserves the user's data goes first, ahead of other features and fixes. That means capturing material that would otherwise be lost, landing what is captured but never imported, and stopping writes that overwrite what a person wrote. Such issues carry the `preservation` label. Pick work from `gh issue list --label next`, then `--label preservation`, then the rest. File an issue that fits under `preservation`.

This file is procedure: how to work here. Facts about the code drift, so they belong in the docstring of the module that enforces them. When this file disagrees with the code, remove the passage rather than correct it.

All changes require tests. Test names: `test_<feature>_<scenario>_<expected_result>`. Use `conftest.py` fixtures; snapshot tests for complex output.

Code standards: Python 3.12+, ruff at 120 chars, mypy, type hints throughout.

User-facing changes are documented in one place each: options in the command's `--help` (its docstrings), behaviour across commands in `docs/handbook.md`, and anything a user must do by hand after upgrading as an entry under the handbook's Upgrading, named by the release. README.md is the overview, and changes only when the overview does: a new command, source or capability.

Pre-commit hooks run ruff and mdformat. If mdformat reformats a file, re-stage and retry the commit.

Commits: imperative mood, concise. Keep the `Co-Authored-By` trailer — it records provenance, not credit. Commit each logical change separately in multi-step plans.

Versions: semver, from git tags (versioningit). Every PR carries exactly one label: `semver:major` (an existing user or repo must adapt: a removed command or flag, a persisted format older releases can't read), `semver:minor` (new, backward-compatible functionality) or `semver:patch` (fixes, docs, CI). Merging tags the merge commit with the bumped version; publishing to PyPI stays manual (`just publish`). Until 1.0, label a breaking change `semver:minor`: `semver:major` is reserved for the PR that declares 1.0. The plugin's own version is separate (below).

## Plugins

`plugins/commonplace-skills/` contains Claude Code skills and agents (version in `.claude-plugin/plugin.json`). These are **end-user tools** — they run inside a user's *commonplace repository* (their knowledge base), not in this Python codebase. Do not use them here.

A PR that changes the plugin bumps its version in its own commit (minor for behaviour changes), unless main already carries an unreleased bump: skills judge staleness by the release in `generated.by`.

**Skills:**

- `/synthesize [topic]` — gather and distil a topic from the commonplace
- `/resonate <slug1> <slug2> [...]` — surface interference patterns between synthesized topics
- `/rake` — surface unmade ideas, todos and projects; propose where to file them in `notes/`
- `/project <sketch>` — draft one project note, `notes/projects/{slug}.md`, or review and update an existing one
- `/dream` — the agent dreams the commonplace from random fragments, each phase in a fresh subagent, then reflects on it in its journal

**Artefact paths** (no dated filenames — git is the versioning layer):

- `topics/{slug}.md` (the distillation); no generated index pages: skills list folders on demand with `commonplace ls`
- `topics/resonances/{sorted-slugs}.md`
- `.commonplace/skills/synthesize/{slug}.md` — a topic's gathering
- `notes/ideas.md`, `notes/todo.md`, `notes/projects/{slug}.md` — the user's own notes; `/rake` and `/project` only add what the user approves
- `.commonplace/skills/{skill}/` — skill-managed state nobody reads for its own sake (e.g. `rake/chaff.md`, items dropped in triage); never a source. Artefacts a person reads stay visible
- `.commonplace/skills/dream/{agent}/{yyyy}/{mm}/{date}-{slug}.md` — a dream's telling, kept as skill state; beside it `{date}-{slug}.trace.md`, for debugging and read by nobody: the residue, and how far the reflection found it. The agent's self-contained reflection on the dream goes in `agent-journal/{agent}/`

**Conventions:**

- Concepts that cut across skills (artefact kinds, attribution, citations, review) are defined once in `plugins/commonplace-skills/concepts.md`; each skill restates inline, by name, the rules it acts on and points there
- The run lifecycle (preflight, worktree, spawn, review, commit, agent journal, land) is defined once in `plugins/commonplace-skills/operating-model.md`; each skill names those steps as its own headings and supplies only its approval step, paths and commit message, so each procedure has one copy
- Heavy work (search, read, write) runs in a `general-purpose` subagent whose prompt is the skill's `subagent.md`, read by path; the calling agent handles survey, review, and commit
- Artefacts update in place on incremental runs; prior state is recoverable via git
- Everything under `topics/` is an OKF v0.2 concept document (`type: Topic`). The spec is vendored verbatim at `.claude/reference/okf-spec.md` (knowledge-catalog@62432a0, Apache-2.0); read it there rather than fetching. The repo root is the bundle; dot-directories are outside it. Staleness is `generated.by` (`<skill>/<plugin release>`) against the skill's newest Conventions entry, which is named by the release that introduced it
- Distillations and resonances carry a `## Revisions` section — one appended line per run, so the trajectory stays visible in-band rather than only in `git log`
- Gatherings quote from primitives only (`chats/`, `journal/`, `notes/`) and attribute every quote to a speaker; `topics/**` is derived and is never a source
