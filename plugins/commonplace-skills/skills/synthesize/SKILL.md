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

Get the lay of the land:

```bash
commonplace stats
```

If no topic argument was provided, run broad searches to discover recurring
themes:

```bash
commonplace search -n 50 "<broad query>"
```

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

If the user requests changes, either ask the subagent to revise (spawn
another subagent with the correction) or make small edits directly.

### 4. Update the Map (optional)

If synthesizing multiple topics, or if a map already exists, update or create:
`topics/map.md`

### 5. Commit

Stage and commit using `commonplace git`:

```bash
commonplace git -- add topics/{slug}/
commonplace git -- commit -m "Synthesize: {topic name}"
```

If a pre-commit hook (e.g. a formatter) modifies files, the commit will fail.
Re-stage the reformatted files and retry — this is expected behaviour, not an
error:

```bash
commonplace git -- add topics/{slug}/
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

### Phase 2: Gather

Run at least 3-5 searches with different phrasings:

```bash
commonplace search -n 30 "<specific query>"
```

**Search strategy:** After initial searches, check coverage by source
directory (chats, journal, notes) — if any is unrepresented, run a targeted
query for it. Breadth of querying matters; there is no systematic way to know
what you missed.

**Triage before deep reading.** For topics with many hits (>15 sources), do a
triage pass first: skim each source (first ~100 lines or the section around
the search hit) and rank by relevance. Only do full reads of the top sources.
Use background subagents to parallelise reading of large files.

Read each relevant source in full (use the Read tool). For each relevant
section:

- Note the date (from file path or frontmatter)
- Extract the relevant passage
- Track the source path

Order all gathered material chronologically.

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

> Relevant passage text...

## <date> — <title or context>
*<repo-relative source path>*

> Relevant passage text...
```

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
Open questions, unresolved tensions, areas for future exploration.

### Most Pressing Thread
The single open question or tension most worth the user's attention right now.
```

Reference the gathering in `source_gathering`.

### Incremental Mode

When `topics/{slug}/gathering.md` and `topics/{slug}/distillation.md` already
exist, this is an update run:

1. **Read the existing distillation** to understand current coverage.
1. **Search for new material** — focus on dates after the gathering's most
   recent source. You don't need to re-read already-gathered sources.
1. **Update `gathering.md` in place** — append new entries in chronological
   order. Update `updated` and `sources` in the frontmatter. Update `queries`
   if new queries were used.
1. **Update `distillation.md` in place** — revise Timeline, Shifts, and
   Threads to reflect new material. Note what changed. Update `updated`.

Git tracks the full history. The prior state is always recoverable.

### Return Value

When both artefacts are written, return **only** this compact summary — do
not print the file contents:

______________________________________________________________________

**Gathering**: N sources, {earliest date} to {latest date}

**Distillation**:

- Timeline: \<2-3 sentence summary>
- Shifts: \<2-3 sentence summary>
- Threads:
  - <Thread name>: <one sentence>
  - *(repeat for each thread)*
  - **Most Pressing Thread**: <Thread name> — <one sentence rationale>

**Artefacts written**:

- `topics/{slug}/gathering.md`
- `topics/{slug}/distillation.md`

______________________________________________________________________

______________________________________________________________________

## Guidelines

- **Quote generously** in gatherings — but scale quoting inversely with source
  count. 5 sources: quote everything relevant. 20 sources: quote turning points,
  summarise the rest.
- **Be specific** in distillations. Cite dates and sources, not vague summaries.
- **Name the threads**. The most valuable output is often what's unresolved.
- **Don't over-synthesize**. If the material is thin, say so. A short
  distillation noting "only 2 sources, early exploration" is more honest than
  padding.
- **Trajectory over state**: each synthesis run is additive. Don't try to
  produce a "final" summary. The accumulation IS the value — now via git
  history rather than dated filenames.
- **Missteps remain**: if a prior distillation got something wrong, the new one
  corrects it in place — but git preserves the prior state.
