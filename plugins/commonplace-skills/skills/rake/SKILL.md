---
name: rake
description: Rake the commonplace for unmade things at every scale and propose where to file them
---

# Rake for Intentions

You are raking a commonplace repository for **unmade things at every scale**:
a one-line idea, a committed action, a multi-month project. Rake through the
whole commonplace, then rake what turns up into heaps for the user to sort.

**Propose, don't file.** The repository already has a destination for each
scale, and deciding which one an item belongs in is the user's call:

| Scale   | Destination                | Meaning                                     |
| ------- | -------------------------- | ------------------------------------------- |
| Idea    | `notes/ideas.md`           | uncommitted backlog: no commitment, no date |
| Todo    | `notes/todo.md`            | committed, for a given year                 |
| Project | `notes/projects/{slug}.md` | a larger effort, with a note of its own     |

The motivating failure: an agent filed an essay split as a committed todo,
and the user decided it was still only an idea. Nothing is written until the
user has triaged it.

The heavy scanning runs in a subagent. You handle survey, triage, filing, and
commit. Use `/project` to draft or update a single project note once `/rake`
has surfaced it.

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

### 1. Survey

Find when the last rake was filed:

```bash
commonplace git -- log -1 --format='%ad' --date=short --grep='^Skill: rake@'
```

Check which destinations exist (`notes/ideas.md`, `notes/todo.md`,
`notes/projects/`). A missing one is not an error; triage will offer to create
it.

### 2. Spawn

**Spawn** as in `operating-model.md`, with `description`
`"Rake for intentions"`, `${CLAUDE_PLUGIN_ROOT}/skills/rake/subagent.md`, and
this placeholder:

- `last_rake` — the date from step 1, or `never`

### 3. Triage

Triage is this skill's **Review**, as in `operating-model.md`, with two
checks of its own, since both are invisible once filed:

- **Attribution.** Every proposal rests on the *user's* words, or on an
  agent's suggestion the user explicitly took up. Drop any whose only
  evidence is an agent speaking.
- **Silence** is evidence of neither abandonment nor completion: for
  *stopped* and *unclear* items, ask.

Present the subagent's heaps to the user in its order. For each proposal the
user chooses one of:

- **idea** — file in `notes/ideas.md`
- **todo** — file in `notes/todo.md`, under a year the user names
- **project** — list in `notes/projects/`, and offer `/project`
- **done** — it happened; say where if the user wants it recorded
- **drop** — not a live intention; tombstone it as chaff (see step 4)

If your harness has a multiple-choice question tool, triage through it rather
than a prose list.

Take the suggested destination as a suggestion only. When the user hesitates
between two scales, file at the smaller one: promoting an idea later is
cheap, while a false commitment nags.

For the **already filed** heap, ask only about items the subagent flagged as
possibly done or as having an overturned premise; the user decides whether to
tick, strike, or edit them.

Triage answers are decisions, not evidence: they land where they are filed,
and rake keeps no separate review record.

### 4. File

Write only what the user accepted. The destinations are the user's own notes,
not derived artefacts, so:

- **Follow each file's conventions, not a template.** Read its header and
  sections first and match them: checkbox style, section per year or per
  kind, line wrapping. Add to an existing section rather than inventing one;
  if nothing fits, ask.
- **Add; don't rewrite.** Never reorder, reword, or reformat the user's
  existing entries. The only changes to existing lines are ones the user
  asked for in triage (ticking, striking, editing).
- **One line per item**, in the user's voice, followed by the primitive it
  came from as a root-relative wikilink (the path without `.md`), e.g.
  `- [ ] Split the attention essay in two ([[/chats/claude/2026/03/2026-03-14-attention]])`.
  Check the target exists as `<path>.md` before writing it.
- **Project-scale items** get a line in `notes/projects/index.md` if it
  exists, following its sections. Offer to run `/project <slug>` for each; if
  the user accepts, run it in-session.
- **Missing destination.** If a destination file doesn't exist, ask before
  creating it, and give it a one-line italic header saying what belongs there.

**Dropped items** go to `.commonplace/skills/rake/chaff.md`, one line each, so
the next rake doesn't propose them again:
`- <headline, verbatim> — dropped <YYYY-MM-DD>. Sources: <paths>.`
This is skill state, not a note: the headlines are the subagent's, not the
user's, so it lives outside `notes/` where nothing will quote it as evidence.
Create it without asking, headed
`*Raked up and dropped. Delete a line to let /rake propose it again.*`
The file is hidden, so tell the user its path and how many lines it now holds.

Show the user the diff and wait for approval.

### 5. Commit

**Commit** as in `operating-model.md`:

```bash
commonplace --root "$PWD" git -- add notes/ .commonplace/skills/rake/
commonplace --root "$PWD" git -- commit -m "Rake: file {n} intentions" -m "Skill: rake@{plugin version}"
```

The trailer is how the next run finds this one.

### 6. Agent Journal (optional)

This step is yours: **Agent journal** in `operating-model.md`.

### 7. Land

**Land** as in `operating-model.md`. The user's approval in step 4 is the
go-ahead.
