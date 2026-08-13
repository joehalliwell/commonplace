---
name: synthesize
description: Discover and synthesize topics from the commonplace
argument-hint: '[topic]'
---

# Synthesize Topics

You are performing topic synthesis on a commonplace repository. The heavy work
(searching, reading, writing artefacts) runs in a subagent to keep this
context clean. You handle survey, review, and commit.

## Prerequisites

The commonplace must have an index. If search returns errors, ask the user to
run `commonplace index` first.

## Workflow

### 1. Survey

Get the lay of the land, and index *before* gathering rather than only after:

```bash
commonplace index
commonplace stats
```

A stale index silently omits the most recent chats — exactly the material most
likely to have moved a topic on. Indexing is incremental, so this is cheap
when nothing has changed.

If no topic argument was provided, run broad searches to discover recurring
themes:

```bash
commonplace search -n 50 "<broad query>"
```

Seed those queries from the repository rather than from guesswork: the
provider and date spread in `commonplace stats`, the titles of recently
modified notes (`commonplace git -- log --oneline -20 --name-only`), and any
existing `topics/index.md` entries — a topic already synthesized is evidence
of what the user cares about, and its threads suggest what's adjacent.

Propose 3-5 candidate topics to the user. Wait for confirmation before
proceeding.

If a topic argument WAS provided, skip discovery and proceed directly to
step 2.

### 2. Spawn the Synthesis Subagent

Use the **Task tool** to spawn a `general-purpose` subagent:

- `description`: `"Synthesize: {topic}"`
- `subagent_type`: `"general-purpose"`
- `prompt`: Use the **Subagent Prompt Template** section below, substituting
  all `{placeholders}`:
  - `{topic}` — the confirmed topic name (e.g. "memory and continuity")
  - `{slug}` — kebab-case slug (e.g. "memory-and-continuity")
  - `{date}` — today as YYYY-MM-DD
  - `{working_dir}` — absolute path to the repository root

Wait for the subagent to complete before continuing. It will return a compact
review summary and the paths of the written artefacts.

### 3. Review

**Present the subagent's summary to the user.** Do not re-read the artefact
files — the subagent already produced the summary in the required format.
Wait for the user to approve, request changes, or redirect. Do not proceed to
commit without explicit approval.

Two things are worth checking in the summary before you present it, because
both are invisible once committed:

- **Attributed claims.** If a Shift or Thread describes how the *user's*
  thinking changed, the summary should make clear that's whose thinking it
  was — not an assistant's framing the user never took up.
- **Overstated endings.** Language like "abandoned" or "gave up on" is a
  claim about intent. Chats stop for logistical reasons; if the subagent has
  read silence as a decision, flag it.
- **Cryptic lines.** The subagent has just read everything and writes as
  though you have too. If a thread or shift only makes sense to someone
  holding the sources in mind — an unexplained coinage, a "this tension" with
  no antecedent, a thread name standing in for the question — send it back to
  be restated rather than passing it on. You cannot repair this at review
  time: you haven't read the sources either, so guessing at what was meant
  puts an invention into the record.

If the user requests changes, either ask the subagent to revise (spawn
another subagent with the correction) or make small edits directly.

If the subagent returned **Stopped — overlaps `{existing-slug}`** instead of
a summary, no artefacts were written. Put the choice to the user — extend the
existing topic, or fork this one anyway — and re-spawn with their answer.

### 4. Update the Topic Index

Write or update `topics/index.md` so the topic is discoverable by the next
run, by `/resonate`, and by the user. Same shape as `projects/index.md`:

```markdown
---
kind: topic-index
updated: <YYYY-MM-DD>
---

# Topics

- [{slug}]({slug}/) — updated <YYYY-MM-DD>, N sources
  **Pressing**: <the Most Pressing Thread, one line>
```

One entry per topic, alphabetical by slug. Take the source count and pressing
thread straight from the subagent's summary — don't re-read the artefacts.
Leave other topics' entries untouched.

### 5. Commit

Stage and commit using `commonplace git`:

```bash
commonplace git -- add topics/{slug}/ topics/index.md
commonplace git -- commit -m "Synthesize: {topic name}"
```

If a pre-commit hook (e.g. a formatter) modifies files, the commit will fail.
Re-stage the reformatted files and retry — this is expected behaviour, not an
error:

```bash
commonplace git -- add topics/{slug}/ topics/index.md
commonplace git -- commit -m "Synthesize: {topic name}"
```

Then re-index so the new artefacts are searchable:

```bash
commonplace index
```

______________________________________________________________________

## Subagent Prompt Template

Fill in all `{placeholders}` and pass the result as the `prompt` argument to
the Task tool.

______________________________________________________________________

You are performing topic synthesis in a commonplace repository.

**Context**

- Repository root: `{working_dir}`
- Topic: {topic}
- Slug: {slug}
- Date: {date}

Your job is to check for prior work, gather sources, and write the gathering
and distillation artefacts. Do **not** commit — return a compact review
summary when done and the calling agent will handle review and commit.

**Commonplace CLI**

```bash
commonplace stats
commonplace search -n 30 "<query>"   # hybrid semantic + full-text
commonplace search -n 5 "<query>"
```

### Phase 1: Check for Prior Work

Before searching sources, check whether this topic has already been distilled:

```bash
commonplace search -n 5 "gathering {topic}"
commonplace search -n 5 "distillation {topic}"
```

Also check directly for existing artefact files:

- `topics/{slug}/gathering.md`
- `topics/{slug}/distillation.md`

If prior artefacts exist, read them now — they establish existing coverage and
determine whether this is a first-run or an update (see Incremental Mode
below).

**Check for overlap with existing topics.** An exact slug match is not enough:
topics accrete, and nothing else stops `memory-and-continuity`, `continuity`
and `persistence` becoming three topics that gather the same chats and never
learn about each other. So:

```bash
ls topics/
```

Read `topics/index.md` if it exists, and the `queries` frontmatter of any
topic whose slug or entry looks adjacent to `{slug}`. If a substantial part of
what you'd gather is already gathered elsewhere, **stop and say so in your
return value** rather than proceeding — name the overlapping topic and offer
the choice between extending it and forking a new one. Two thin overlapping
topics are worse than one thick one, and merging them later means reconciling
two Revisions histories by hand.

Proceed without asking when the overlap is incidental — shared vocabulary,
a handful of sources in common.

### Phase 2: Gather

Run at least 3-5 searches with different phrasings:

```bash
commonplace search -n 30 "<specific query>"
```

**Search strategy:** After initial searches, check coverage by source
directory (chats, journal, notes) — if any is unrepresented, run a targeted
query for it. Breadth of querying matters; there is no systematic way to know
what you missed.

**Gather only from primitives.** Sources are `chats/`, `journal/`, `notes/` —
the captured record. Never quote `topics/**` into a gathering: distillations,
resonances and the topic index are *derived* artefacts, and prior runs commit
and re-index them, so they will surface in your search results alongside real
sources. Quoting one launders synthesis back into evidence, counts the same
claim twice, and breaks the provenance chain — every claim must bottom out at
something captured, not something previously concluded. Prior work on this
topic is read in Phase 1 to establish coverage; it is not a source.

**Triage before deep reading.** For topics with many hits (>15 sources), do a
triage pass first: skim each source (first ~100 lines or the section around
the search hit) and rank by relevance. Only do full reads of the top sources.
Use background subagents to parallelise reading of large files.

Read the sources that survive triage in full (use the Read tool). For each
relevant section:

- Note the date (from file path or frontmatter)
- Extract the relevant passage
- **Note who said it** — transcripts mark speakers with `## Human` /
  `## Claude` (or whatever names the serializer was configured with)
- Track the source path

Order all gathered material chronologically.

**Attribution is not optional.** A quote with no speaker is worse than no
quote: an assistant's speculative riff, gathered unattributed, comes back a
year later as evidence of how the user's own thinking evolved. Most sources
here are conversations *with* an assistant, so this is the default failure
mode, not an edge case. Every quote carries its speaker.

### Phase 3: Write the Gathering

Write to: `topics/{slug}/gathering.md`

```markdown
---
kind: gathering
queries:
  - "<search query 1>"
  - "<search query 2>"
updated: <YYYY-MM-DD>
sources:
  - <repo-relative path to source 1>
  - <repo-relative path to source 2>
---

# Gathering: {topic}

## <date> — <title or context>
*<repo-relative source path>*

**<speaker>:**
> Relevant passage text...

**<speaker>:**
> Relevant passage text...

## <date> — <title or context>
*<repo-relative source path>*

**<speaker>:**
> Relevant passage text...
```

Where a passage only makes sense as an exchange, quote both turns in order
rather than collapsing them into one attributed block.

**Density.** Quote generously when sources are few (\<10). For larger topics,
quote verbatim only the most significant passages (turning points, novel
formulations, contradictions) and summarise the rest. A gathering too long to
read defeats its purpose.

### Phase 4: Distil

Synthesize in two passes.

**First pass — structure.** Produce the Timeline and Shifts sections:

- **Timeline**: When did this topic appear? Key dates and milestones.
- **Shifts**: How has thinking evolved? What changed and why?

**Second pass — tensions.** Re-read the gathering specifically looking for
contradictions, unresolved questions, and gaps. Produce:

- **Threads**: What's unresolved? What dangling questions remain?

The Threads section is the most valuable part of a distillation. Give it the
most attention. At the end of Threads, call out one **Most Pressing Thread**
— the single open question or tension most worth the user's attention right
now.

**Chats end for logistical reasons.** Context limits, session timeouts, an
interruption at the desk. The end of a transcript is not a conclusion, and a
line of thought going quiet is not evidence it was abandoned. Before calling
anything dropped:

- **Search for it resuming elsewhere.** Continuation in a *later, separate
  chat* is the normal shape here — the transcript boundary is an artefact of
  logistics, not a boundary of thought.
- **Distinguish closed from stopped.** *Closed*: explicitly resolved, or set
  aside in so many words. *Stopped*: the transcript simply ends, often
  mid-exchange or on an unanswered question. Say which you mean.
- **When you can't tell, say so.** "Last touched 2026-03-14, no visible
  resolution" is honest and useful. "Abandoned in March" is a fabrication
  about the user's intent.

The same caution applies to **Shifts**: an apparent change of mind is often
just a new chat that never picked up the old framing. A framing that stops
recurring may have been settled, superseded, or merely interrupted — and only
the first two are shifts.

**Write to be read cold.** You are finishing a run in which you have just read
every source, so the compressed phrase feels sufficient — it isn't. The reader
is someone months from now with none of that in mind: the user, a later
synthesis run, `/resonate`, or a search hit that surfaces one section with no
surrounding context. Assume they have not read the gathering and will not go
and read it.

In practice:

- **Nothing refers outside the document.** No "the earlier framing", "this
  tension", "as discussed" pointing at material the reader can't see. Name the
  thing — "the framing of memory as storage rather than relationship" — then
  you may refer back to it.
- **Expand coinages on first use.** Vocabulary invented mid-chat ("the
  legibility problem", "melange", "the archive move") is opaque outside the
  conversation that minted it. Gloss it once, in a clause, then use it freely.
- **Every section stands alone.** Chunking splits artefacts by section for the
  index, so a reader can land in Threads having never seen Timeline. Don't
  make a section depend on one above it.
- **Prefer the concrete noun to the abstract one.** "The tension between
  shipping and rewriting" beats "the aforementioned tension".

A distillation that only its author can read is a private note, and the whole
point is that it outlives the run that wrote it.

**Cite claims to passages, not to the gathering as a whole.** The frontmatter
points at `gathering.md`; that's provenance to a file, which leaves a reader
unable to check "the framing shifted in March" without re-reading everything.
Each substantive claim carries an inline `(<date>, <source path>)`, and where
the claim is about who thought what, name the speaker too. Provenance has to
bottom out at a passage.

Write to: `topics/{slug}/distillation.md`

```markdown
---
kind: distillation
queries:
  - "<search query 1>"
  - "<search query 2>"
updated: <YYYY-MM-DD>
source_gathering: topics/{slug}/gathering.md
---

# Distillation: {topic}

## Timeline
Key dates and evolution of the topic.

## Shifts
How thinking has changed. What prompted the shifts.

## Threads
Open questions, unresolved tensions, areas for future exploration. Mark each
thread *closed*, *stopped*, or *unclear*, with the date it was last touched:

- **<Thread name>** — *stopped*, last touched <date>.
  <The open question, stated in full and readable on its own.>

### Most Pressing Thread
<The single question or tension most worth attention now, stated in full,
followed by why it matters.>

## Revisions
- <YYYY-MM-DD> — <what this run added, changed, or corrected>
```

Reference the gathering in `source_gathering`.

**Thread names are labels, not content.** "The opacity problem" tells a reader
nothing; the line under it has to carry the question in full — "does making
the work legible to an audience cost it the ambiguity that made it worth
making?" A thread whose statement is shorter than its name is a bookmark for
you, not a thread for the reader.

The **Most Pressing Thread** has a mechanical reason to stand alone: step 4
copies it verbatim into `topics/index.md`, where it appears next to other
topics with none of this document around it. If it doesn't survive that move,
it's too cryptic. Write it as a full sentence naming its own subject.

**The Revisions section carries the trajectory.** Distillations are updated in
place, so without it every run silently overwrites the last and the only
record of how the reading changed is a diff nobody reads — invisible to the
search index, which sees the working tree alone. One line per run:

- On a first run: `<date> — First distillation, N sources.`
- On an update: what new material arrived and what it changed. Name
  corrections explicitly — "March's reading of X as Y was wrong; the later
  chats show Z" — because a correction that silently replaces its predecessor
  erases the misstep, and the record is supposed to include missteps.
- If a run added sources but changed no conclusions, say that. It's a real
  finding: the reading held.

Newest entries at the bottom. Never rewrite or prune existing lines.

Each line names what actually changed. "Updated Shifts and Threads" records
nothing a reader can use — it describes which headings you touched, not what
the distillation now says that it didn't before. "Added 6 chats from July;
the Shifts section previously had the move to weekly notes as a productivity
decision, and the July material shows it was about legibility to other
people" is a line worth keeping. It should be intelligible to someone who
never sees the diff.

### Incremental Mode

When `topics/{slug}/gathering.md` and `topics/{slug}/distillation.md` already
exist, this is an update run:

1. **Read the existing distillation** to understand current coverage.

1. **Search for new material** — re-run the queries recorded in the
   gathering's frontmatter, plus any new phrasings, and compare the hits
   against its `sources` list. Anything not already listed is new material,
   **whatever its date**. You don't need to re-read sources already on the
   list.

   Do not filter by "newer than the last run". Imports backfill: a fresh
   export or a fetch that reaches further back adds *old* conversations to
   the repository, and a date cutoff skips them silently. The `sources` list
   is the record of what has actually been read; diff against that.

1. **Update `gathering.md` in place** — append new entries in chronological
   order. Update `updated` and `sources` in the frontmatter. Update `queries`
   if new queries were used.

1. **Update `distillation.md` in place** — revise Timeline, Shifts, and
   Threads to reflect new material. Update `updated`.

1. **Append a Revisions line** recording what this run changed. This is the
   only in-band record that the distillation moved.

If the existing distillation has no `## Revisions` section, it predates the
convention. Add the section and open it with a single line — e.g.
`<date> — Revision tracking begins; entries above predate it.` — then append
this run's line. Do not attempt to reconstruct earlier runs from git history,
and do not retro-attribute speakers in gathering entries you haven't
re-read: a guess in the record is worse than an acknowledged gap.

Git tracks the full history. The prior state is always recoverable.

### Guidelines

- **Attribute every quote.** Whose thought was this? See Phase 2.
- **Gather from primitives only.** Never cite `topics/**` as a source.
- **Interruption is not abandonment.** See Phase 4. Applies to both Threads
  and Shifts.
- **Quote generously** in gatherings — but scale quoting inversely with source
  count. 5 sources: quote everything relevant. 20 sources: quote turning points,
  summarise the rest.
- **Be specific** in distillations. Every substantive claim carries an inline
  `(<date>, <source path>)` — provenance bottoms out at a passage, not a file.
- **Name the threads**. The most valuable output is often what's unresolved —
  but a name is not a thread. State each open question in full.
- **Write to be read cold.** See Phase 4. Nothing refers outside the document;
  every section stands alone; coinages get glossed on first use. This applies
  to the return summary too — it is the only thing the user sees before
  approving the commit.
- **Don't over-synthesize**. If the material is thin, say so. A short
  distillation noting "only 2 sources, early exploration" is more honest than
  padding.
- **Trajectory over state**: each synthesis run is additive. Don't try to
  produce a "final" summary. The accumulation IS the value — now via git
  history rather than dated filenames.
- **Missteps remain**: if a prior distillation got something wrong, the new one
  corrects it in place — and names the correction in Revisions, so the misstep
  stays legible to a reader rather than only to `git log`.

### Return Value

If you stopped in Phase 1 on a substantial overlap, return only:

______________________________________________________________________

**Stopped — overlaps `{existing-slug}`**

- What that topic already covers: <one or two sentences>
- What `{slug}` would add that it doesn't: <one or two sentences>
- Recommendation: \<extend `{existing-slug}` / fork `{slug}` anyway>

______________________________________________________________________

Otherwise, when both artefacts are written, return **only** this compact
summary — do not print the file contents.

Compact does not mean cryptic. This summary is what the user reads to decide
whether to commit, and they have not read the artefacts. Each line must make
sense to someone who has seen neither the sources nor the distillation.

______________________________________________________________________

**Gathering**: N sources, {earliest date} to {latest date}

**Distillation**:

- Timeline: \<2-3 sentence summary>
- Shifts: \<2-3 sentence summary>
- Threads:
  - <Thread name>: \<the open question, stated in full> — *(closed / stopped
    / unclear)*
  - *(repeat for each thread)*
  - **Most Pressing Thread**: <Thread name> — <one sentence rationale>

**This run changed**: \<the Revisions line, verbatim>

**Coverage**: \<thin / adequate / rich> — \<any gap worth naming, e.g. "nothing
from journal/", "all 4 sources within one week">

**Artefacts written**:

- `topics/{slug}/gathering.md`
- `topics/{slug}/distillation.md`

______________________________________________________________________
