# CLAUDE.md

How to work in this repository. `MANIFESTO.md` is the northstar for system design: read it before changing what the system does. A rule that belongs to one module is stated in that module's docstring, so read the docstring before changing the module.

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
