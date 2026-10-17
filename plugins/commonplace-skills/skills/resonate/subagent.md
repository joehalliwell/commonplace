# Resonate: Subagent

The calling agent's prompt gives a value for each `{placeholder}` outside the
Return Value.
Braces in the Return Value are yours to fill.

You are surfacing cross-topic resonance in a commonplace repository.

**Context**

- Repository root: `{working_dir}`
- Topics: {topics}
- Slugs: {slugs}
- Output path: `{output_path}`
- Review log: `{review_log}`
- Date: {date}
- Plugin release: {version}

Read `{concepts}` first. It defines the terms this prompt uses: *primitive*,
*laundering*, *attribution*, *closed / stopped / unclear*, *written to be read
cold*.

Read the distillations, find the interference patterns between them, and
write the resonance. Leave committing to the calling agent: return the
compact summary below.

### Phase 1: Read the Distillations

Read each `topics/{slug}.md` in full, noting its key threads (above all the
Most Pressing Thread), vocabulary and concerns that recur across topics, and
framings that contradict each other.

If `{output_path}` exists, this is an update run: read it, and note what has
changed in the distillations since. Read `{review_log}` too, if it exists:
each `## <date> — Review` entry is the user's own words from reviewing an
earlier run, and full evidence, honoured on every run. The log is the calling
agent's to append to.

### Phase 2: Search for Cross-Topic Material

Search the intersections you found, for material no single-topic gathering
captured:

```bash
commonplace search -n 20 "<concept from topic A> <concept from topic B>"
```

**Quote only primitives**: `chats/`, `journal/`, `notes/`. The distillations
named above are your inputs; any other `topics/**` hit is laundering.

**Carry attribution and citations through** from the distillations, and cite
anything new the same way. A crossing is far weaker if both passages turn out
to be an agent's phrasing rather than the user's own.

### Phase 3: Write the Resonance

Write to `{output_path}`:

```markdown
---
type: Topic
kind: resonance
title: {topics}
description: <one sentence: the ground these topics share or contest>
topics:
  - <slug 1>
  - <slug 2>
source_distillations:
  - topics/<slug 1>.md
  - topics/<slug 2>.md
generated: {by: resonate/{version}, at: <now, e.g. 2026-10-01T14:00:00Z>}
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
**<One sentence naming the topics it arises between and stating the
question.>**

## Revisions
- <YYYY-MM-DD> — <one sentence: what the resonance now says that it didn't>
```

`description` says what ground the topics share or contest, which holds from
run to run. Write `generated` every time you write the file; `verified` is
the calling agent's, added after review.

**Revisions** are the in-band record that the reading moved: append one
sentence per run saying what changed, and leave existing lines as written. A
resonance with no such section gets one, opened with
`<date> — Revision tracking begins; entries above predate it.`

**Write to be read cold.** A resonance is two steps from anything concrete
(about distillations, which are about sources), and its reader has read
neither distillation:

- Each crossing and tension restates what each topic contributes: not "both
  circle the same legibility problem" but what that problem is in each.
- Name the topics in every reference ("art", not "the former").
- Gloss one topic's vocabulary before using it about another.

**The resonance is the field between the topics.** The distillations already
summarise each one; the value is what no topic alone could say:

- Tensions are worth as much as crossings: a sharp contradiction beats a
  vague overlap.
- Name questions precisely: "does the career's need for legibility contradict
  the art's investment in opacity?", not "how do these relate?".
- Keep the few crossings and tensions with the most charge: three sharp ones
  beat ten loose ones. Where two topics barely touch, say so.

**Update runs** note what has shifted since the last resonance: crossings
that emerged, tensions that sharpened. A tension resolves only when something
in the material resolves it. Distillations mark threads *closed*, *stopped*
or *unclear*; a *stopped* thread stays an open tension ("untouched since
March, still open").

### Citations

- Carry the distillations' root-relative wikilinks through, and cite new
  quotes the same way: `[[/<source path without .md>]]`. Rewrite an older
  `(<date>, <path>)` citation as the plain wikilink. Where a date is the
  point, it goes in the sentence or as `[<date>](/<path>.md)`.
- *(<speaker>, in review, <date>)* citations, from the distillations or the
  review log, stay plain text: they point into skill state.
- **Every target resolves.** Before returning, confirm each `[[/<path>]]`
  exists as `<path>.md`. A missing file has usually moved:
  `find chats journal notes -name '<basename>.md'`, and cite where it is now.

### Return Value

Return **only** this summary, written to be read cold:

______________________________________________________________________

**Crossings**: \<2-3 sentence summary of the strongest overlaps>

**Tensions**: \<2-3 sentence summary of the sharpest contradictions>

**Generative Questions**:

- <question>
- *(repeat)*
- **Most Live Question**: \<its headline, verbatim>

**This run changed**: \<the Revisions line, verbatim>

**Artefact written**: `{output_path}`

______________________________________________________________________
