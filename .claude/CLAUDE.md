# CLAUDE.md

How to work in this repository. `MANIFESTO.md` is the northstar for system design: read it before changing what the system does. A rule that belongs to one module is stated in that module's docstring, so read the docstring before changing the module.

## Principles

What a change must keep true, whatever the code is called.

1. **Capture, interpret, index.** Data flows one way: fetch captures, import or render interprets, index makes searchable. Each stage reads only the one before it, so each can be replayed from it. Archives are primitive, notes are renderings that can be regenerated, and the index is a cache nobody commits.
1. **Capture is total and dumb; interpretation is revisable.** A fetcher keeps everything verbatim, because whatever it drops is gone for good. Every judgement lives in import, where a later release can make it again from the same archive.
1. **What is seen is a tree**: the repository is the shadow of a graph no one can see whole (MANIFESTO). A person browses a tree of files: by where (the source or agent), then when (year, month, date), named by title. It shows lossily a graph of anything kept, said or referred to, at any grain, where a node needs no file: "alice" unlinked in prose is an edge to her all the same. A chat's archive holds forks, tool calls and subagents its note flattens; most references in prose are unresolved. Keep structure the tree can't show, and prefer changes that make an implied edge explicit. Not every node is a note: a blob is one, kept under `.commonplace/`, and a source or a person is one with no file. A note's path is its id, chosen readable because people browse the tree: a vendor's id only finds which note a new capture belongs to, and a note keeps its first path, because links and marginalia hang off it.
1. **One writer per note**, as things stand. A note's writer is the process whose output it is: import renders chats, a mirror copies upstream state, a person writes journal and notes, a skill derives topics. A writer may overwrite its own committed output; nothing overwrites another's, nor anything uncommitted. Everything else said about a note goes in its marginalia.
1. **Git is the trajectory.** Every write is a commit of exactly what it wrote, so any prior state can be recovered: no dated filenames, no version suffixes.
1. **Provenance bottoms out at primitives.** A rendered note names the archive it came from; a derived artefact is never cited as a source.
1. **Every persisted format carries a version.** Readers refuse a newer one, keep reading older ones, and the repo keeps an example of each.
1. **LLM work goes in skills.** The tooling stays deterministic, for now: anything that needs judgement (synthesis, triage, titling) is a skill run in an agent session over the CLI, and the CLI does what gives the same answer every time.
1. **Data preservation first**: see Workflow.

## Commands

```bash
just test                              # Tests with coverage
uv run pytest tests/test_import.py -v  # One test file
just update-snapshots                  # Rewrite snapshot tests' expected output
just format                            # ruff fix + format
just lint                              # What CI checks: ruff and mypy
just install                           # Install the CLI editable; rerun after dependency changes. Main checkout only: in a worktree it repoints the CLI there
just publish                           # Build and publish to PyPI
```

## Workflow

Priorities: work that preserves the user's data goes first, ahead of other features and fixes. That means capturing material that would otherwise be lost, landing what is captured but never imported, and stopping writes that overwrite what a person wrote. Such issues carry the `preservation` label. Pick work from `gh issue list --label next`, then `--label preservation`, then the rest. File an issue that fits under `preservation`.

This file is procedure: how to work here. Facts about the code drift, so they belong in the docstring of the module that enforces them. When this file disagrees with the code, remove the passage rather than correct it.

All changes require tests. Test names: `test_<feature>_<scenario>_<expected_result>`. Use `conftest.py` fixtures; snapshot tests for complex output.

Type hints throughout; `just lint` must pass.

User-facing changes are documented in one place each: options in the command's `--help` (its docstrings), behaviour across commands in `docs/handbook.md`, and anything a user must do by hand after upgrading as an entry under the handbook's Upgrading, named by the release. README.md is the overview, and changes only when the overview does: a new command, source or capability.

Pre-commit hooks run ruff and mdformat. If mdformat reformats a file, re-stage and retry the commit.

Commits: imperative mood, concise. Keep the `Co-Authored-By` trailer — it records provenance, not credit. Commit each logical change separately in multi-step plans.

Versions: semver, from git tags (versioningit). Every PR carries exactly one label: `semver:major` (an existing user or repo must adapt: a removed command or flag, a persisted format older releases can't read), `semver:minor` (new, backward-compatible functionality) or `semver:patch` (fixes, docs, CI). Merging tags the merge commit with the bumped version; publishing to PyPI stays manual (`just publish`). Until 1.0, label a breaking change `semver:minor`: `semver:major` is reserved for the PR that declares 1.0. The plugin's own version is separate (below).

## Plugins

`plugins/commonplace-skills/` holds end-user tools: they run inside a user's commonplace repository, not in this codebase. Do not use them here.

A PR that changes the plugin bumps its version (`.claude-plugin/plugin.json`) in its own commit (minor for behaviour changes), unless main already carries an unreleased bump: skills judge staleness by the release in `generated.by`.

Writing skills:

- Define a concept that cuts across skills once, in `concepts.md`, and the run lifecycle once, in `operating-model.md`. A skill restates by name the rules it acts on and points there, so each procedure has one copy.
- Put heavy work (search, read, write) in a `general-purpose` subagent whose prompt is the skill's `subagent.md`, read by path. The calling agent does survey, review and commit.
- Give artefacts paths without dates, and update them in place: git is the versioning layer.
- A change to what a skill writes adds an entry to its conventions, named by the release that ships it, so `generated.by` can say which artefacts are stale.
- Read the OKF spec at `.claude/reference/okf-spec.md`, vendored verbatim, rather than fetching it.
