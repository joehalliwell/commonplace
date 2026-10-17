---
name: project
description: Draft a project note, or review and update an existing one, from the commonplace
argument-hint: <sketch or slug>
---

# Draft a Project Note

You are drafting or updating one project note, `notes/projects/{slug}.md`, in
a commonplace repository. The argument is a sketch: a slug (`commonplace`), a
rough name (`interviewing counter cultural luminaries`), or a short
description. Use it as a search seed. `/rake` is the usual way a project gets
here.

A project note is the **user's own note**, not a derived artefact. You draft
it from the record; the user owns it afterwards. Running `/project` on an
existing note **reviews and updates** it in place. The user approves the diff
before commit, and git holds every prior state.

The heavy work runs in a subagent. You handle slug derivation, review, and
commit.

## Prerequisites

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` and
`${CLAUDE_PLUGIN_ROOT}/operating-model.md` first: the concepts every skill
shares, and how every run goes from preflight to landing. The steps below
restate the rules they act on, and name the operating model's steps where
they run them.

## Workflow

### 0. Preflight and Enter

**Preflight** and **Enter** as in `operating-model.md`: settle uncommitted
files with the user, refresh the index, then work in a worktree
fast-forwarded to their branch.

### 1. Derive the Slug

Convert the sketch to a kebab-case slug. If ambiguous, confirm with the user.
Check `notes/projects/` for an existing note under this or a similar name; if
one exists, this is an update run on that file.

### 2. Spawn

**Spawn** as in `operating-model.md`, with `description`
`"Project note: {sketch}"`, `${CLAUDE_PLUGIN_ROOT}/skills/project/subagent.md`,
and these placeholders:

- `sketch` — the user's original sketch
- `slug` — the derived slug

### 3. Review

**Review** as in `operating-model.md`, showing the diff of
`notes/projects/{slug}.md` after the summary, with checks of this skill's
own:

- On an update run, every edit outside Status, History and Next appears in
  the summary's Edits list with a source, and no existing History line
  changed; History only grows.
- The First Next Action holds up against the full Next list; flag dependency
  reasoning that looks off.
- The summary's Questions go to the user.

If the user rejects an edit, revert that hunk
(`commonplace --root "$PWD" git -- checkout -p notes/projects/{slug}.md`) or
make the correction directly.

Review words go in the note itself: it is the user's, so a correction or
answer becomes an edit to it. Where one adds a milestone, append a History
line citing it.

### 4. Commit

If `notes/projects/index.md` exists, add or update the project's line there,
following the file's own sections and style, leaving other entries as they
are. Then **Commit** as in `operating-model.md`:

```bash
commonplace --root "$PWD" git -- add notes/projects/
commonplace --root "$PWD" git -- commit -m "Project note: {sketch}"
```

### 5. Agent Journal (optional)

This step is yours: **Agent journal** in `operating-model.md`.

### 6. Land

**Land** as in `operating-model.md`. The user's approval in step 3 is the
go-ahead.
