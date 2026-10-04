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

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` first: the concepts every skill
shares, with their reasons. The steps below restate the rules they act on.

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

### 2. Spawn the Rake Subagent

Use the **Task tool** to spawn a `general-purpose` subagent:

- `description`: `"Rake for intentions"`
- `subagent_type`: `"general-purpose"`
- `prompt`: Use the **Subagent Prompt Template** below, substituting:
  - `{date}` — today as YYYY-MM-DD
  - `{working_dir}` — absolute path to the repository root
  - `{last_rake}` — the date from step 1, or `never`
  - `{concepts}` — the absolute path of `${CLAUDE_PLUGIN_ROOT}/concepts.md`

### 3. Triage

Before presenting, check the proposals the way you'd check a distillation,
because all of these are invisible once filed:

- **Attribution.** Every proposal rests on the *user's* words, or on an
  agent's suggestion the user explicitly took up. Drop any whose only
  evidence is an agent speaking.
- **Silence** is evidence of neither abandonment nor completion: for
  *stopped* and *unclear* items, ask.
- **Cold reading.** List every term, name, or reference in the proposals you
  couldn't explain from the proposals alone, and send a non-empty list back
  to the subagent before presenting.

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

```bash
commonplace git -- add notes/ .commonplace/skills/rake/
commonplace git -- commit -m "Rake: file {n} intentions" -m "Skill: rake@{plugin version}"
```

If a pre-commit hook reformats files, re-stage and retry. The trailer is how
the next run finds this one.

Then re-index:

```bash
commonplace index
```

### 6. Agent Journal (optional)

This step is yours. Write what the work left you with: reflections the
material prompted, candid opinions of the user and what you'd do about them.
What came up with the user stays in this run's output, never here. **Agent
journal** in `concepts.md` says where the entry goes and how. If nothing
comes, skip it; if you write one, commit it on its own and tell the user its
path:

```bash
commonplace git -- add agent-journal/
commonplace git -- commit -m "Agent journal: {agent}"
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

Read `{concepts}` first. It defines the terms this prompt uses: *primitive*,
*attribution*, *closed / stopped / unclear*, *backfill*, *written to be read
cold*.

Find **live intentions**: things the user means to make or do that aren't
done. Your output is proposals only, in the return value; the calling agent
triages them with the user and files what's accepted.

**Commonplace CLI**

```bash
commonplace search -n 30 "<query>"
```

### Phase 1: Read What's Already Filed

Read `notes/ideas.md`, `notes/todo.md`, and every `notes/projects/*.md`
(including `index.md`), where they exist. Note each open item, the section it
sits in, and its checkbox state. These are what you must not re-propose.

Read `.commonplace/skills/rake/chaff.md` too, if it exists: items the user dropped in an earlier
rake, each with its drop date. Don't re-propose one unless the user raised it
again in a source dated *after* the drop. If so, propose it and say it was
dropped on that date.

### Phase 2: Stopped Threads in Topic Distillations

Every thread in a topic's distillation, `topics/*.md`, has the form
`- **<question>** — *(closed|stopped|unclear)*, last touched <date>.`
Collect the *stopped* and *unclear* ones. Entries are line-wrapped, so find
the status marker and read the whole entry around it. Topics not yet
conformed to the flat layout are still `topics/*/distillation.md`:

```bash
grep -n -E '— \*(stopped|unclear)\*' topics/*.md topics/*/distillation.md 2>/dev/null
```

Most are open questions and belong to `/synthesize`, not here. Keep only those
that name an **unmade thing**: an essay, an interview, a prototype, a talk, a
release.

Distillations are derived, so **cite the primitive**: follow each kept
thread's inline citation to the passage it names (`chats/`, `journal/`,
`notes/`, `memory/`) and read it there. Keep the thread only if the passage
shows the user intending to make the thing.

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

**Attribution.** Transcripts mark speakers with `## Human` / `## Claude` (or
the configured names). A plan counts when the user stated it, or an agent
suggested it and the user took it up in so many words ("yes, let's do that",
"I'll do the second one"); an unanswered "next steps" list stays the agent's.

Read chats of every date (backfill: an old plan may be new to the
repository). Phase 1 is what stops re-proposals.

### Phase 4: Plans in Agent Memory

Agent memory is mirrored under `memory/<agent>/`. If it exists, read every
file updated since the last rake, or all of them if there was none. A memory
is an agent's paraphrase of the user, so treat each plan in it as a
candidate, not as the user's words: search for the originating passage and
cite it. If you find none, cite the memory file and say the plan rests on it
alone. If there is no `memory/`, name that gap under Coverage.

### Phase 5: Heap

**One proposal per unmade thing.** The same essay plan will surface as a
stopped thread, in two chats, and in the journal. Merge them, and list every
source.

For each proposal decide:

- **Status**, in the same vocabulary as distillation threads:

  - *closed*: done, or set aside in so many words. Don't propose it; if it's
    filed as open, report it under Already Filed as possibly done.
  - *stopped*: the user stated it, then the record goes quiet; it may have
    been done offline.
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
deciding. Each headline is one sentence naming the thing to be made: "an
essay arguing that attention is a commons", not "the essay". Gloss any
coinage from the chats.

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
