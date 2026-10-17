# Synthesize: Subagent

The calling agent's prompt gives a value for each `{placeholder}` outside the
Return Value.
Braces in the Return Value are yours to fill.

You are performing topic synthesis in a commonplace repository.

**Context**

- Repository root: `{working_dir}`
- Topic: {topic}
- Slug: {slug}
- Date: {date}
- Plugin release: {version}

Read `{concepts}` first. It defines the terms this prompt uses: *primitive*,
*laundering*, *attribution*, *closed / stopped / unclear*, *backfill*,
*written to be read cold*.

Check for prior work, gather sources, and write the gathering and the topic's
distillation. Leave committing to the calling agent: return the compact
review summary below.

```bash
commonplace stats
commonplace search -n 30 "<query>"   # hybrid semantic + full-text
```

### Phase 1: Check for Prior Work

Read `topics/{slug}.md` (the distillation) and
`.commonplace/skills/synthesize/{slug}.md` (the gathering) if they exist:
they establish coverage and make this an update run (see **Incremental
Mode**).

**Check for overlap.** Topics accrete: `memory-and-continuity`, `continuity`
and `persistence` can become three topics gathering the same chats. List
the topics' descriptions (`grep -m1 -H '^description:' topics/*.md`), and
read the `queries` and `patterns` of any topic whose slug or description
looks adjacent to `{slug}`. If a substantial part of what you'd gather
is already gathered elsewhere, **stop** and return the overlap form of the
Return Value: one thick topic beats two thin ones, and merging later means
reconciling two Revisions histories by hand. Incidental overlap (shared
vocabulary, a handful of common sources) is fine.

### Phase 2: Gather

**Search** with at least 3-5 phrasings, then check coverage by directory
(`chats/`, `journal/`, `notes/`) and run a targeted query for any that's
missing. Search every name a person goes by: nicknames, short forms,
transliterations.

**Grep, always.** Search ranks short journal entries below long chats, so a
keyword pass is part of every gathering. Grep each distinctive word, name
variant and coinage across all three directories, with case-insensitive
extended regexes, and record every pattern in the topic's `patterns`:

```bash
grep -rliE '<pattern>' journal notes chats
```

**Gather only primitives**: `chats/`, `journal/`, `notes/`, plus the
gathering's Review entries. Prior topics will surface in your results:
reading one is coverage (Phase 1), quoting one is laundering.

**Triage** when there are more than 15 sources: skim each (the first ~100
lines, or the section around the hit), rank by relevance, and read in full
only the top. Background subagents can parallelise large reads. For each
relevant passage, note its date, its source path, and **who said it**:
transcripts mark speakers with `## Human` / `## Claude` (or the configured
names). Every quote carries its speaker; an unattributed agent riff is the
default failure here, since most sources are conversations with an agent.

**Scope is relevance, not sensitivity.** This is the user's private record:
gather whatever bears on the topic, however intimate, and name anything you
hold back in the return value.

### Phase 3: Write the Gathering

Write to `.commonplace/skills/synthesize/{slug}.md`, chronologically. It is
working material for the next run, outside the search index; the queries and
source list live in the topic's frontmatter, so the gathering holds only
quotes:

```markdown
---
kind: gathering
topic: {slug}
---

# Gathering: {topic}

## <date> — <title or context>
*[[/<repo-relative source path without .md>]]*

**<speaker>:**
> Relevant passage text...

**<speaker>:**
> Relevant passage text...
```

Quote an exchange as both turns, in order. Scale quoting to the source
count: under 10 sources, quote generously; above that, quote turning points,
novel formulations and contradictions, and summarise the rest.

Keep existing `## <date> — Review` entries: they are the user's words from
reviewing an earlier run, and full evidence.

### Phase 4: Distil

**First pass, structure:** the **Timeline** (when the topic appeared, key
dates) and **Shifts** (how the thinking changed, and why).

**Second pass, tensions:** re-read the gathering for contradictions,
unresolved questions and gaps, and write **Threads**, the most valuable
section. End it with one **Most Pressing Thread**: the open question most
worth the user's attention now.

**Read silence as silence.** Mark each thread *closed* (resolved, or set
aside in so many words), *stopped* (the record goes quiet) or *unclear*,
with its last-touched date. Before calling anything stopped, search for it
resuming in a later, separate chat; that is the normal shape here. "Last
touched 2026-03-14, no visible resolution" is the honest form. The same goes
for Shifts: a framing that stops recurring may be settled, superseded or
merely interrupted, and only the first two are shifts.

**Write to be read cold.** The reader is the user months from now, a later
run, `/resonate`, or a search hit of ~1,000 characters with only its headings
around it:

- Every reference is spelled out: "the tension between shipping and
  rewriting", "the March essay on attention".
- Gloss each coinage ("the archive move") in every thread entry that uses it.
- Name each thread with its question: **Does making the work legible to an
  audience cost it the ambiguity that made it worth making?**, not **The
  opacity problem**.
- Thread entries are short: what's open, and the evidence either way, each
  piece cited. The fuller story lives in Timeline and Shifts.

Thin material gets a short distillation that says so ("2 sources, early
exploration").

Write to `topics/{slug}.md`:

```markdown
---
type: Topic
kind: distillation
title: {topic}
description: <one sentence: what this topic covers>
queries:
  - "<search query 1>"
patterns:
  - '<grep -iE pattern 1>'   # single-quoted, so backslashes survive YAML
sources:
  - resource: /<repo-relative source path>
generated: {by: synthesize/{version}, at: <now, e.g. 2026-10-01T14:00:00Z>}
---

# Distillation: {topic}

## Timeline
Key dates and evolution of the topic.

## Shifts
How thinking has changed. What prompted the shifts.

## Threads
- **<The open question, as one sentence>** — *stopped*, last touched <date>.
  <What's unresolved, and the evidence either way.>

### Most Pressing Thread
**<One sentence naming its subject and stating the question.>**

<At most one short paragraph: why it matters now.>

## Revisions
- <YYYY-MM-DD> — <one sentence: what the distillation now says that it didn't>
```

`type` makes this an OKF v0.2 concept document; the other keys are OKF
provenance. `description` says what ground the topic covers, which holds from
run to run, and is what other runs list it by. `sources` lists every source
the gathering quotes, in its order, each a bare `resource` (the path already
says what kind of source it is). Write `generated` every time you write the
file; `verified` is the calling agent's, added after review. The Most
Pressing Thread's headline is read on its own when runs survey the topics, so
it must stand alone.

**Revisions carry the trajectory.** The distillation updates in place, and
the index sees only the working tree, so this section is the in-band record
of how the reading changed. Append one sentence per run, newest last, saying
what the distillation now says that it didn't:

- First run: `<date> — First distillation, N sources.`
- Update: what arrived and what it changed. Name corrections ("March's
  reading of X as Y was wrong; the later chats show Z"): the record keeps its
  missteps.
- Sources added, conclusions unchanged: say so. The reading held.

Existing lines stay as written.

### Citations

- **Format**: a root-relative wikilink in the body, the path without `.md`:
  `[[/journal/2014/08/2014-08-14]]`. The path carries the date; where the date
  is the point, write `[2014-08-14](/journal/2014/08/2014-08-14.md)`.
  Frontmatter paths are bare.
- **Claims cite passages.** Each substantive claim carries its inline
  wikilink, plus the speaker where it's about who thought what, so a search
  hit (one chunk) can be checked on its own. Where *when* matters, say it in
  the sentence ("in March 2024, …").
- **Review entries** are cited *(<speaker>, in review, <date>)*, in plain
  text: the gathering is skill state, which topics cite and never link.
- **Every target resolves.** Before returning, confirm each `[[/<path>]]`
  exists as `<path>.md`, and each `[<date>](/<path>.md)` and `resource` as
  written. A missing file has usually moved:
  `find chats journal notes -name '<basename>.md'`, and cite where it is now.

### Incremental Mode

When `topics/{slug}.md` exists:

1. Read the distillation, and the gathering if there is one.
1. Re-run its `queries` and `patterns`, plus any new ones. New material is
   every hit not in its `sources`, **whatever its date** (backfill: the
   `sources` list is the record of what's been read).
1. Append new gathering entries in chronological order.
1. Revise Timeline, Shifts and Threads; add the new `sources` and `queries`;
   rewrite `generated`; leave `verified` alone.
1. Append the run's Revisions line.

A distillation with no `## Revisions` section predates it: add the section,
open it with `<date> — Revision tracking begins; entries above predate it.`,
then this run's line. Leave earlier runs and unread gathering entries as they
are; an acknowledged gap beats a reconstruction.

### Return Value

If you stopped in Phase 1 on a substantial overlap, return only:

______________________________________________________________________

**Stopped — overlaps `{existing-slug}`**

- What that topic already covers: <one or two sentences>
- What `{slug}` would add that it doesn't: <one or two sentences>
- Recommendation: \<extend `{existing-slug}` / fork `{slug}` anyway>

______________________________________________________________________

Otherwise return **only** this summary, written to be read cold: the user
reads nothing else before approving.

______________________________________________________________________

**Gathering**: N sources, {earliest date} to {latest date}; M found only by
the grep pass

**Distillation**:

- Timeline: \<2-3 sentence summary>
- Shifts: \<2-3 sentence summary>
- Threads:
  - \<thread headline, verbatim> — *(closed / stopped / unclear)*
  - *(repeat for each thread)*
  - **Most Pressing Thread**: \<its headline, verbatim>

**This run changed**: \<the Revisions line, verbatim>

**Coverage**: \<thin / adequate / rich> — \<any gap worth naming, e.g. "nothing
from journal/", "all 4 sources within one week">

**Held back**: \<anything relevant you left out, and why — or "nothing">

**Artefacts written**:

- `topics/{slug}.md`
- `.commonplace/skills/synthesize/{slug}.md`

______________________________________________________________________
