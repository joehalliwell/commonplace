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

`topics/index.md` lists the available topics with their pressing threads —
read it to resolve partial or misspelled slugs, and to suggest combinations
when the user is vague about what to put alongside what.

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

If a crossing, tension or question in the summary only makes sense to someone
who has just read both distillations, send it back to be restated. You have
not read them either, so rewriting it yourself would put a guess into the
record.

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

Quote such material from **primitives only** — `chats/`, `journal/`, `notes/`.
Other `topics/**` artefacts will appear in these results, since every run
commits and re-indexes; they are derived, and quoting one into a resonance
stacks synthesis on synthesis. The distillations named above are your inputs;
nothing else under `topics/` is.

Distillations attribute claims to speakers and cite `(<date>, <source path>)`.
Carry both through. A crossing between two topics is a different and much
weaker thing if the two passages turn out to be an assistant's phrasing in
both places rather than the user's own.

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
<The single question thrown up by this combination that most demands
attention — stated in full, naming the topics it arises between, and
readable by someone who has read none of the source material.>

## Revisions
- <YYYY-MM-DD> — <what this run added, changed, or corrected>
```

Resonances update in place, so the Revisions section is the only in-band
record that this reading moved. One line per run, appended, never rewritten,
each naming what actually changed rather than which headings you touched. If
an existing resonance has no such section, add it and open with
`<date> — Revision tracking begins; entries above predate it.`

**Write to be read cold — this artefact needs it most.** A resonance is
written *about* distillations, which were themselves written about sources,
so its shorthand sits two removes from anything concrete. A crossing phrased
as "both topics circle the same legibility problem" is unreadable to anyone
who hasn't just read both distillations, and nobody ever has.

- Restate what each topic contributes, in the crossing itself. The reader has
  not read either distillation and will not open them.
- Gloss vocabulary that belongs to one topic before using it across both —
  a term of art from the art topic lands in the career topic as noise.
- Name topics explicitly rather than "the former" / "the latter" / "the
  first topic". With three or more slugs this is the difference between a
  legible artefact and a puzzle.
- A Generative Question that only parses with both distillations in mind
  isn't generative. It's a note to self.

**What to avoid:**

- Don't summarise each topic independently — the distillations already exist
  for that.
- Don't force connections that aren't there. If two topics barely touch, say
  so.
- Don't be exhaustive in Crossings or Tensions. Identify the ones with the
  most charge.

### Guidelines

- **The resonance is not a meta-summary.** It's the field generated by placing
  the topics in proximity. The value is in what couldn't be said about any
  topic alone.

- **Tensions are as valuable as crossings.** A sharp contradiction between two
  topics is more interesting than a vague overlap.

- **Name the questions precisely.** Vague questions ("how do these relate?")
  have no value. Precise ones ("does the career's need for legibility
  contradict the art's investment in opacity?") do. Note that the good example
  names both topics and states the tension outright — precise and
  self-contained are the same discipline here.

- **Write to be read cold.** Restate what each topic contributes rather than
  gesturing at its distillation; name topics instead of "the former"; gloss
  one topic's vocabulary before using it about another. Short is not the same
  as cryptic — cut words, not the referents.

- **Short is better.** A resonance that tries to say everything says nothing.
  Three sharp crossings beat ten loose ones.

- **Carry attribution and citations through** from the distillations.

- **Update, don't replace.** On an update run, note what has shifted since the
  last resonance — new crossings that emerged, tensions that sharpened.

  A tension is only **resolved** if something in the material resolves it. A
  thread that stopped being discussed has not resolved: chats end for
  logistical reasons — context limits, timeouts, an interruption at the desk —
  and a topic can go quiet for months and resume unchanged. Distillations now
  mark threads as *closed*, *stopped*, or *unclear*; respect that distinction
  and don't upgrade a *stopped* thread to a resolved tension. "Untouched since
  March, still open" is the honest form.

### Return Value

When the artefact is written, return **only** this compact summary:

______________________________________________________________________

**Crossings**: \<2-3 sentence summary of the strongest overlaps>

**Tensions**: \<2-3 sentence summary of the sharpest contradictions>

**Generative Questions**:

- <question>
- *(repeat)*
- **Most Live Question**: <question>

**This run changed**: \<the Revisions line, verbatim>

**Artefact written**: `{output_path}`

______________________________________________________________________
