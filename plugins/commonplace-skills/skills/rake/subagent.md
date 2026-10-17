# Rake: Subagent

The calling agent's prompt gives a value for each `{placeholder}` outside the
Return Value.
Braces in the Return Value are yours to fill.

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
