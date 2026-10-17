# Commonplace Operating Model

How every skill run that writes goes, from start to landing. `concepts.md`
says what the artefacts are; this file says how a run makes them. Each skill
names these steps as its own headings and supplies only what differs:

- the step where the user approves its output;
- the paths it stages, and its commit message.

The run works in a git worktree, so its changes land on the user's branch as
one fast-forward or not at all. `commonplace` acts on the root checkout
(`COMMONPLACE_ROOT`) whatever the cwd: search, stats, index and history there
are what the run should read; only the run's writes and commits go to the
worktree.

## Preflight

In the root checkout, before writing anything. Note the branch, and check for
uncommitted files:

```bash
commonplace git -- branch --show-current
commonplace git -- status --porcelain
```

If there are any, list the paths and ask:

- **Sync**: `commonplace sync` commits everything, pulls and pushes. If it
  fails, stop and report.
- **Continue**: leave them. The run won't see them, and landing refuses only
  if the run wrote the same paths.
- **Cancel**: stop, so the user can look into it with their own tools.

## Enter

`EnterWorktree`, then fast-forward it to the noted branch, so the worktree
holds what the index searches (it starts from the remote's default branch,
which lags local imports):

```bash
git merge --ff-only {branch}
```

If that fails, stop and report. Note the worktree's path and branch: landing
needs them. Everything the run writes goes in the worktree, subagents
included: give them the worktree's path as `{working_dir}`, and run any git
that changes files with `commonplace --root "$PWD" git`.

## Commit

In the worktree, after approval, staging exactly the paths the run wrote:

```bash
commonplace --root "$PWD" git -- add {paths}
commonplace --root "$PWD" git -- commit -m "{message}"
```

A pre-commit hook that reformats files fails the commit: re-stage them and
retry the same commit. Never push the worktree branch.

## Agent journal

Optional, and the agent's own. What came up with the user belongs in the
run's output (see **Review** in `concepts.md`); this is for what the work left
the agent with: reflections the material prompted, however loose; what it
makes of the user, unflattering included, and what it would do about it; how
the run went. Candour over tact: the user would rather read an opinion than a
polite one. If nothing comes, skip it.

Write it in `agent-journal/{agent}/{yyyy}/{mm}/{yyyy-mm-dd}.md`, where
`{agent}` is the agent running the skill, e.g. `claude-code` (see
**Nomenclature** in `concepts.md`). If `agent-journal/README.md` exists, its
conventions win. Otherwise: the entry is the agent's, not the user's; the user
may read it; later sessions won't remember this one, so write it to be read
cold. Append if today's file exists; head a new one like the user's journal,
e.g. `# Thursday, October 1 2026`.

Commit it on its own, on the run's branch, so one fast-forward carries the
whole run, and tell the user its path:

```bash
commonplace --root "$PWD" git -- add agent-journal/
commonplace --root "$PWD" git -- commit -m "Agent journal: {agent}"
```

## Land

The user's approval of the run's output is the go-ahead to merge: don't ask
again. `ExitWorktree` with `action: keep`, then:

```bash
commonplace git -- merge --ff-only {worktree branch}
commonplace git -- worktree remove {worktree path}
commonplace git -- branch -d {worktree branch}
commonplace index
```

If the merge fails (the branch moved, or it would overwrite uncommitted
files), stop and report, leaving the worktree and branch for the user. Never
rebase, and never push: the user's sync does that.
