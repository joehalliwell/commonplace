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

The motivating failure: an assistant filed an essay split as a committed todo,
and the user decided it was still only an idea. Nothing is written until the
user has triaged it.

The heavy scanning runs in a subagent. You handle survey, triage, filing, and
commit. Use `/project` to draft or update a single project note once `/rake`
has surfaced it.

## Prerequisites

The commonplace must have an index. If search returns errors, ask the user to
run `commonplace index` first.

## Workflow

### 1. Survey

Index first, so the most recent chats are searchable:

```bash
commonplace index
```

Find when the last rake was filed:

```bash
commonplace git -- log -1 --format='%ad' --date=short --grep='^Skill: rake@'
```

Check which destinations exist (`notes/ideas.md`, `notes/todo.md`,
`notes/projects/`). A missing one is not an error; triage will offer to create
it.

**Ask the user about plans held outside the commonplace.** An assistant's
memory (for example a claude.ai memory, or a Claude-held todo list) can hold
plans that never reached the repository, and the subagent cannot see them.
Ask: *"Is there anything an assistant is remembering for you that I should
include? Paste it, or say no."* Pass whatever they give you through as
`{assistant_plans}`, verbatim, or `none`.

### 2. Spawn the Rake Subagent

Use the **Task tool** to spawn a `general-purpose` subagent:

- `description`: `"Rake for intentions"`
- `subagent_type`: `"general-purpose"`
- `prompt`: Use the **Subagent Prompt Template** below, substituting:
  - `{date}` — today as YYYY-MM-DD
  - `{working_dir}` — absolute path to the repository root
  - `{last_rake}` — the date from step 1, or `never`
  - `{assistant_plans}` — from step 1

Wait for the subagent to complete.

### 3. Triage

Before presenting, check the proposals the way you'd check a distillation,
because all of these are invisible once filed:

- **Whose plan is it?** Every proposal must rest on the *user's* words, or on
  an assistant's suggestion the user explicitly took up. An assistant's list
  of next steps is not the user's plan. Drop any proposal whose only evidence
  is an assistant speaking.
- **Silence is not abandonment, nor completion.** A plan that stopped in a
  chat may have been done offline, or set aside, or merely interrupted. For
  *stopped* and *unclear* items, ask rather than assume.
- **Cold reading.** List every term, name, or reference in the proposals that
  you couldn't explain from the proposals alone. If the list isn't empty, send
  it back to the subagent before presenting.

Present the subagent's heaps to the user in its order. For each proposal the
user chooses one of:

- **idea** — file in `notes/ideas.md`
- **todo** — file in `notes/todo.md`, under a year the user names
- **project** — list in `notes/projects/`, and offer `/project`
- **done** — it happened; say where if the user wants it recorded
- **drop** — not a live intention

Take the suggested destination as a suggestion only. When the user hesitates
between two scales, file at the smaller one: promoting an idea later is
cheap, while a false commitment nags.

For the **already filed** heap, ask only about items the subagent flagged as
possibly done or as having an overturned premise; the user decides whether to
tick, strike, or edit them.

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
  came from, e.g. `- [ ] Split the attention essay in two (chats/claude/2026/03/2026-03-14-attention.md)`.
- **Project-scale items** get a line in `notes/projects/index.md` if it
  exists, following its sections. Offer to run `/project <slug>` for each; if
  the user accepts, run it in-session.
- **Missing destination.** If a destination file doesn't exist, ask before
  creating it, and give it a one-line italic header saying what belongs there.

Show the user the diff and wait for approval.

### 5. Commit

```bash
commonplace git -- add notes/
commonplace git -- commit -m "Rake: file {n} intentions" -m "Skill: rake@{plugin version}"
```

If a pre-commit hook reformats files, re-stage and retry. The trailer is how
the next run finds this one.

Then re-index:

```bash
commonplace index
```

______________________________________________________________________

## Subagent Prompt Template

______________________________________________________________________

You are raking a commonplace repository for unmade things at every scale:
ideas, committed actions, projects.

**Context**

- Repository root: `{working_dir}`
- Date: {date}
- Last rake: {last_rake}
- Plans held by an assistant, pasted by the user: {assistant_plans}

Your job is to find **live intentions**: things the user means to make or do
that aren't done. Do not write or edit any file. Return proposals; the calling
agent triages them with the user and files what's accepted.

**Commonplace CLI**

```bash
commonplace search -n 30 "<query>"
```

### Phase 1: Read What's Already Filed

Read `notes/ideas.md`, `notes/todo.md`, and every `notes/projects/*.md`
(including `index.md`), where they exist. Note each open item, the section it
sits in, and its checkbox state. These are what you must not re-propose.

### Phase 2: Stopped Threads in Topic Distillations

Every thread in a `topics/*/distillation.md` has the form
`- **<question>** — *(closed|stopped|unclear)*, last touched <date>.`
Collect the *stopped* and *unclear* ones. Entries are line-wrapped, so find
the status marker and read the whole entry around it:

```bash
grep -n -E '— \*(stopped|unclear)\*' topics/*/distillation.md
```

Most are open questions and belong to `/synthesize`, not here. Keep only those
that name an **unmade thing**: an essay, an interview, a prototype, a talk, a
release.

Distillations are derived. **Never cite one.** Follow each kept thread's
inline citation back to the primitive it names (`chats/`, `journal/`,
`notes/`) and read the passage there. If the passage doesn't show the user
intending to make the thing, drop it.

### Phase 3: Stated Plans in Chats and the Journal

Search for the user stating a plan. Run all of these:

```bash
commonplace search -n 30 "I'll write"
commonplace search -n 30 "I want to make"
commonplace search -n 30 "I'm going to"
commonplace search -n 30 "plan to"
commonplace search -n 30 "next step is"
commonplace search -n 30 "working on"
commonplace search -n 30 "I should"
commonplace search -n 30 "one day I'd like to"
commonplace search -n 30 "idea for"
```

Read the journal directly: every entry since the last rake, or the last
twelve months if there was none. Journal entries are the user's own words
and often the richest source.

**Attribution is critical.** Transcripts mark speakers with `## Human` /
`## Claude` (or whatever names the serializer was configured with). A plan
counts only if:

- the user stated it, or
- an assistant suggested it and the user took it up in so many words ("yes,
  let's do that", "I'll do the second one").

An assistant's "next steps" list that the user didn't answer is not a plan.

Chats are not filtered by date: imports backfill old conversations, so an old
plan may be new to the repository. Phase 1 is what stops re-proposals.

### Phase 4: Plans Held by an Assistant

If `{assistant_plans}` is not `none`, treat each item as a candidate. Search
the commonplace for where it came from; if you find the originating passage,
cite it. If you don't, cite `assistant memory` and say so — it's evidence
of a plan, but not a primitive.

### Phase 5: Heap

**One proposal per unmade thing.** The same essay plan will surface as a
stopped thread, in two chats, and in the journal. Merge them, and list every
source.

For each proposal decide:

- **Status**, in the same vocabulary as distillation threads:

  - *closed*: done, or set aside in so many words. Don't propose it; if it's
    filed as open, report it under Already Filed as possibly done.
  - *stopped*: the user stated it, then the record goes quiet. Quiet is not
    evidence either way; it may have been done offline.
  - *unclear*: mixed or thin evidence.

  Always give the date it was last touched.

- **Suggested destination**, by the strength of commitment in the user's own
  words:

  - **idea**: "might", "would be fun to", "one day". No commitment, no date.
  - **todo**: a single action the user committed to ("I'll", "I'm going
    to", a date or deadline).
  - **project**: several steps sustained over time, usually named, usually
    touched in more than one chat.

  When unsure, suggest the smaller commitment.

- **Already filed?** Match against Phase 1. A match is not a proposal. Report
  it under Already Filed only if the scan found something new about it:
  evidence it's done, or a later topic distillation whose Shifts overturn its
  premise. In the second case, cite the primitive that shows the change, not
  the distillation.

**Write to be read cold.** The user reads only your return value before
deciding. Each headline is one sentence naming the thing to be made, with no
pointers outside the text: not "the essay" but "an essay arguing that
attention is a commons". Gloss any coinage from the chats.

### Return Value

Return **only** this, heaps in this order, most recently touched first
within each. Omit empty heaps.

______________________________________________________________________

**Ideas**

- **{Headline sentence}** — *{stopped / unclear}*, last touched {date}.
  {Who said it and what, one sentence.} Sources: {repo-relative paths}.

**Todos**

- *(same form)*

**Projects**

- *(same form)*, suggested slug `{slug}`.

**Already filed** (only items with news)

- **{The filed item, verbatim}** in `{file}` — {possibly done / premise
  overturned}: {evidence, one sentence}. Source: {repo-relative path}.

**Coverage**: {what was read — e.g. "12 stopped threads, 9 searches, journal
since 2026-06-01" — and any gap worth naming}.

______________________________________________________________________
