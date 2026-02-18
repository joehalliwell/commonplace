---
name: resonate
description: Surface cross-topic connections between existing syntheses
argument-hint: <slug1> <slug2> [slug3 ...]
---

# Resonate

You are surfacing interference patterns between two or more synthesized topics
in a commonplace repository. This skill reads the existing distillations and
writes a resonance artefact — not a summary of each topic, but the space
*between* them: where they meet, where they pull apart, and what questions
they generate when placed alongside each other.

The heavy work runs in a subagent. You handle argument parsing, review, and
commit.

## Prerequisites

Each topic must have a distillation at `topics/{slug}/distillation.md`. If
any is missing, ask the user to run `/synthesize {slug}` first.

The commonplace must have an index. If search returns errors, ask the user to
run `commonplace index` first.

## Workflow

### 1. Parse Arguments

The argument is a space-separated list of topic slugs (e.g. `art ai-consciousness career`). Confirm the slugs with the user if ambiguous.

Verify each distillation exists:

```bash
# check e.g. topics/art/distillation.md, topics/ai-consciousness/distillation.md
```

### 2. Determine Output Path

Sort the slugs alphabetically and join with `-` to form a stable, order-independent key:

`topics/resonances/{sorted-slugs}.md`

For example, `art ai-consciousness career` →
`topics/resonances/ai-consciousness-art-career.md`

Check whether this file already exists — if so, this is an update run.

### 3. Spawn the Resonance Subagent

Use the **Task tool** to spawn a `general-purpose` subagent:

- `description`: `"Resonate: {slugs joined with ', '}"`
- `subagent_type`: `"general-purpose"`
- `prompt`: Use the **Subagent Prompt Template** section below, substituting
  all `{placeholders}`:
  - `{topics}` — human-readable list (e.g. "art, AI consciousness, career")
  - `{slugs}` — the slug list (e.g. `["art", "ai-consciousness", "career"]`)
  - `{sorted_key}` — alphabetically sorted, hyphen-joined (e.g.
    `ai-consciousness-art-career`)
  - `{output_path}` — `topics/resonances/{sorted_key}.md`
  - `{date}` — today as YYYY-MM-DD
  - `{working_dir}` — absolute path to the repository root

Wait for the subagent to complete.

### 4. Review

**Present the subagent's summary to the user.** Do not re-read the artefact.
Wait for explicit approval before committing.

If the user requests changes, spawn a revision subagent or make small edits
directly.

### 5. Commit

```bash
commonplace git -- add topics/resonances/
commonplace git -- commit -m "Resonate: {topics}"
```

If a pre-commit hook reformats files, re-stage and retry.

Then re-index:

```bash
commonplace index
```

______________________________________________________________________

## Subagent Prompt Template

Fill in all `{placeholders}` and pass the result as the `prompt` argument to
the Task tool.

______________________________________________________________________

You are surfacing cross-topic resonance in a commonplace repository.

**Context**

- Repository root: `{working_dir}`
- Topics: {topics}
- Slugs: {slugs}
- Output path: `{output_path}`
- Date: {date}

Your job is to read the distillations, find the interference patterns between
them, and write a resonance artefact. Do **not** commit — return a compact
summary when done.

**Commonplace CLI**

```bash
commonplace search -n 20 "<query>"
```

### Phase 1: Read the Distillations

Read each distillation in full:

- `topics/{slug}/distillation.md` for each slug

Take notes on:

- The key threads in each topic (especially the Most Pressing Thread)
- Any vocabulary, concepts, or concerns that recur across topics
- Any apparent contradictions between how the topics are framed

If `{output_path}` already exists, read it — this is an update run. Note what
has changed in the distillations since it was last written.

### Phase 2: Search for Cross-Topic Material

Run targeted searches for the intersections you've identified:

```bash
commonplace search -n 20 "<concept from topic A> <concept from topic B>"
```

This may surface source material that speaks directly to the intersection and
wasn't captured in any single-topic gathering.

### Phase 3: Write the Resonance

Write to: `{output_path}`

```markdown
---
kind: resonance
topics:
  - <slug 1>
  - <slug 2>
updated: <YYYY-MM-DD>
source_distillations:
  - topics/<slug 1>/distillation.md
  - topics/<slug 2>/distillation.md
---

# Resonance: {topics}

## Crossings
Where these topics genuinely meet — shared concerns, overlapping vocabulary,
ideas that appear independently in each.

## Tensions
Where they pull in different directions — contradictions, incompatible
framings, places where progress in one topic creates problems for another.

## Generative Questions
What does each topic ask of the others? Questions that wouldn't arise from
any single topic alone.

### Most Live Question
The single question thrown up by this combination that most demands attention.
```

**What to avoid:**

- Don't summarise each topic independently — the distillations already exist
  for that.
- Don't force connections that aren't there. If two topics barely touch, say
  so.
- Don't be exhaustive in Crossings or Tensions. Identify the ones with the
  most charge.

### Return Value

When the artefact is written, return **only** this compact summary:

______________________________________________________________________

**Crossings**: \<2-3 sentence summary of the strongest overlaps>

**Tensions**: \<2-3 sentence summary of the sharpest contradictions>

**Generative Questions**:

- <question>
- *(repeat)*
- **Most Live Question**: <question>

**Artefact written**: `{output_path}`

______________________________________________________________________

______________________________________________________________________

## Guidelines

- **The resonance is not a meta-summary.** It's the field generated by placing
  the topics in proximity. The value is in what couldn't be said about any
  topic alone.
- **Tensions are as valuable as crossings.** A sharp contradiction between two
  topics is more interesting than a vague overlap.
- **Name the questions precisely.** Vague questions ("how do these relate?")
  have no value. Precise ones ("does the career's need for legibility
  contradict the art's investment in opacity?") do.
- **Short is better.** A resonance that tries to say everything says nothing.
  Three sharp crossings beat ten loose ones.
- **Update, don't replace.** On an update run, note what has shifted since the
  last resonance — new crossings that emerged, tensions that resolved or
  sharpened.
