# Commonplace Operating Model

How every skill run that writes goes, from start to landing. `concepts.md`
says what the artefacts are; this file says how a run makes them. Each skill
names these steps as its own headings and supplies only what differs:

- its subagent's `description` and placeholders;
- its own review checks, and where review words are recorded;
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

Then bring the index up to date, so the newest chats are searchable (it is
incremental and cheap), and note this plugin's release (`version` in
`.claude-plugin/plugin.json`, beside this file) and the user's name:

```bash
commonplace index
commonplace config user
```

If a `commonplace` command a skill names is unknown (`config`, `ls`), the
installed commonplace is older than this plugin: ask the user to update it
before going on.

## Enter

`EnterWorktree`, then fast-forward it to the noted branch, so the worktree
holds what the index searches (it starts from the remote's default branch,
which lags local imports):

```bash
git merge --ff-only {branch}
```

If that fails, stop and report. Note the worktree's path and branch: landing
needs them. Everything the run writes goes in the worktree, subagents
included, and any git that changes files runs as
`commonplace --root "$PWD" git`.

## Spawn

The heavy work (searching, reading, writing) runs in a `general-purpose`
subagent, which keeps your context for the review. Start it with the
`description` the skill names, and this prompt:

```text
Follow {subagent}, with these values for its placeholders:

- working_dir: <the worktree's absolute path>
- date: <today, YYYY-MM-DD>
- concepts: <absolute path of concepts.md, beside this file>
- <each placeholder the skill lists>: <its value>
```

`{subagent}` is the absolute path of the skill's `subagent.md`. The subagent
returns a compact summary, written to be read cold, and the paths it wrote.

## Review

Present the subagent's summary to the user without re-reading what it wrote:
you are the summary's first cold reader. Before presenting, run the skill's
own checks and **cold reading**: list every term, name or reference in the
summary you couldn't explain from it alone. If the list isn't empty, send it
back, continuing the subagent or spawning a revision subagent with the list
and the paths it wrote. The subagent rewrites the lines; you supply the list.

**What the user says in review is a source.** Before revising, record each
correction or addition verbatim where the skill says (**Review** in
`concepts.md`), then pass it to the revision subagent with the correction, or
make small edits directly.

Wait for explicit approval: it is what **Land** acts on. For a derived
artefact, record it as OKF's human review: set `verified` beside `generated`
to `{by: human:<user>, at: <now, e.g. 2026-10-01T14:00:00Z>}`. You write this
line, after approval; the subagent never does.

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
