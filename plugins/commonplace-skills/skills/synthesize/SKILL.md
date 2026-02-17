---
name: synthesize
description: Discover and synthesize topics from the commonplace
argument-hint: '[topic]'
---

# Synthesize Topics

You are performing topic synthesis on a commonplace repository. Synthesis IS a
conversation — you will search, read, gather, distil, and write artefacts
iteratively. The user may intervene at any point to redirect.

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
gathering.

### 2. Gather

**Check for prior work first.** Before searching sources, check whether this
topic has already been distilled:

```bash
commonplace search -n 5 "gathering <topic>"
commonplace search -n 5 "distillation <topic>"
```

If prior distillations exist, read them now — they establish existing coverage
and determine whether to do a full gather or follow the **Incremental
Synthesis** workflow below.

For the chosen topic, run multiple specific searches:

```bash
commonplace search -n 30 "<specific query>"
```

**Search strategy:** Run at least 3-5 queries with different phrasings to
maximise coverage. After initial searches, check results by source directory
(chats, journal, notes) — if any directory is unrepresented, run a targeted
query for it. There is no systematic way to know what you missed, so breadth
of querying matters.

**Triage before deep reading.** For topics with many hits (>15 sources), do a
triage pass first: skim each source (read the first ~100 lines or the section
around the search hit) and rank by relevance. Only do full reads of the most
relevant sources. Use background subagents to parallelise reading of large
files.

Read each source note to get full context (use the Read tool). For each
relevant section:

- Note the date (from the file path or frontmatter)
- Extract the relevant passage
- Track the source path

Order all gathered material chronologically.

### 3. Write the Gathering

Create the gathering artefact at:
`topics/{slug}/{date}-gathering.md`

Where `{slug}` is the kebab-case topic name and `{date}` is today (YYYY-MM-DD).

Use the gathering template format (see below). The gathering is a
**chronological** compilation of relevant passages with source attribution.

**Density.** Quote generously when sources are few (\<10). For larger topics,
be more selective: quote verbatim only the most significant passages (turning
points, novel formulations, contradictions). Summarise the rest with enough
context to be useful. A gathering that's too long to read defeats its purpose.

### 4. Distil

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

Write the distillation at:
`topics/{slug}/{date}-distillation.md`

Reference the gathering. If prior distillations exist, reference the most
recent one in the `prior_distillation` field and note what has changed since.

### 5. Review

**Present both artefacts to the user before committing.** Do not dump the raw
file contents. Instead, present:

- **Gathering**: source count and date range of material covered (e.g. "12
  sources, 2024-03 to 2025-11").
- **Distillation**: a structured summary — brief prose for Timeline and
  Shifts, then each named Thread, ending with the Most Pressing Thread called
  out explicitly.

Wait for the user to approve, request changes, or redirect. Do not proceed to
commit without explicit approval.

### 6. Update the Map (optional)

If synthesizing multiple topics, or if a map already exists, update or create:
`topics/{date}-map.md`

### 7. Commit

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

## Incremental Synthesis

When a `prior_distillation` exists for a topic, the workflow changes:

1. **Read the prior distillation** to understand existing coverage.
1. **Search for new material** — focus on dates after the prior gathering's
   latest source. You don't need to re-read sources already gathered.
1. **Write a new gathering** containing only the new material. Reference the
   prior gathering in the frontmatter.
1. **Write a new distillation** that updates the prior one. Note what changed:
   new entries in the Timeline, revised Shifts, resolved or new Threads.

The prior artefacts remain untouched. The accumulation is the value.

## Artefact Formats

### Gathering

```markdown
---
kind: gathering
queries:
  - "<search query 1>"
  - "<search query 2>"
created: <ISO 8601 timestamp>
sources:
  - <repo-relative path to source 1>
  - <repo-relative path to source 2>
---

# Gathering: <topic>

## <date> — <title or context>
*<repo-relative source path>*

> Relevant passage text...

## <date> — <title or context>
*<repo-relative source path>*

> Relevant passage text...
```

### Distillation

```markdown
---
kind: distillation
queries:
  - "<search query 1>"
  - "<search query 2>"
created: <ISO 8601 timestamp>
source_gathering: <path to the gathering file>
prior_distillation: <path to prior distillation, or null>
---

# Distillation: <topic>

## Timeline
Key dates and evolution of the topic.

## Shifts
How thinking has changed. What prompted the shifts.

## Threads
Open questions, unresolved tensions, areas for future exploration.

### Most Pressing Thread
The single open question or tension most worth the user's attention right now.
```

### Map

```markdown
---
kind: map
created: <ISO 8601 timestamp>
topics:
  - <slug-1>
  - <slug-2>
---

# Topic Map — <date>

## <topic name>
Brief description. N sources, spanning <earliest date> to <latest date>.
Latest distillation: <path>

## <topic name>
...
```

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
  produce a "final" summary. Date everything. The accumulation IS the value.
- **Missteps remain**: if a prior distillation got something wrong, the new one
  corrects it — but the old one stays.
