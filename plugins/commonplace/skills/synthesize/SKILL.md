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
commonplace search --json -n 50 "<broad query>"
```

Propose 3-5 candidate topics to the user. Wait for confirmation before
proceeding.

If a topic argument WAS provided, skip discovery and proceed directly to
gathering.

### 2. Gather

For the chosen topic, search specifically:

```bash
commonplace search --json -n 30 "<specific query>"
```

Read each source note to get full context (use the Read tool). For each
relevant section:

- Note the date (from the file path or frontmatter)
- Extract the relevant passage verbatim
- Track the source path

Order all gathered material chronologically.

Check for prior work:

```bash
commonplace search --json -n 5 "gathering <topic>"
commonplace search --json -n 5 "distillation <topic>"
```

If prior distillations exist, read them — they provide context and should be
referenced.

### 3. Write the Gathering

Create the gathering artefact at:
`topics/{slug}/{date}-gathering.md`

Where `{slug}` is the kebab-case topic name and `{date}` is today (YYYY-MM-DD).

Use the gathering template format (see below). The gathering is a
**chronological** compilation of relevant passages with source attribution.

### 4. Distil

Now synthesize. Produce a distillation that covers:

- **Timeline**: When did this topic appear? Key dates and milestones.
- **Shifts**: How has thinking evolved? What changed and why?
- **Threads**: What's unresolved? What dangling questions remain?

Write the distillation at:
`topics/{slug}/{date}-distillation.md`

Reference the gathering. If prior distillations exist, reference the most
recent one in the `prior_distillation` field and note what has changed since.

### 5. Update the Map (optional)

If synthesizing multiple topics, or if a map already exists, update or create:
`topics/{date}-map.md`

### 6. Commit

```bash
commonplace commit "Synthesize: {topic name}"
```

This stages all changes and triggers auto-indexing, making the new artefacts
searchable for future synthesis runs.

## Artefact Formats

### Gathering

```markdown
---
kind: gathering
query: "<the search query used>"
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
query: "<the search query used>"
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

- **Quote generously** in gatherings. The raw material matters.
- **Be specific** in distillations. Cite dates and sources, not vague summaries.
- **Name the threads**. The most valuable output is often what's unresolved.
- **Don't over-synthesize**. If the material is thin, say so. A short
  distillation noting "only 2 sources, early exploration" is more honest than
  padding.
- **Trajectory over state**: each synthesis run is additive. Don't try to
  produce a "final" summary. Date everything. The accumulation IS the value.
- **Missteps remain**: if a prior distillation got something wrong, the new one
  corrects it — but the old one stays.
