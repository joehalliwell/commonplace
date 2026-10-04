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

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` first: the concepts every skill
shares, with their reasons. The steps below restate the rules they act on.

Each topic must have a distillation at `topics/{slug}.md`. If any is
missing, ask the user to run `/synthesize {slug}` first; if it is still at
`topics/{slug}/distillation.md`, ask them to run `/synthesize {slug}` to
conform it.

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
# check e.g. topics/art.md, topics/ai-consciousness.md
```

Note this plugin's release, `version` in
`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`, and the user's name,
from `commonplace config user`. Both go into the artefact. If
`commonplace config` is an unknown command, the installed commonplace is
older than this plugin: ask the user to update it before going on.

### 2. Determine Output Path

Sort the slugs alphabetically and join with `-` to form a stable, order-independent key:

`topics/resonances/{sorted-slugs}.md`

For example, `art ai-consciousness career` →
`topics/resonances/ai-consciousness-art-career.md`

Check whether this file already exists — if so, this is an update run. Each
resonance records the release that wrote it and when:

```bash
grep -m1 '^generated:' topics/resonances/{sorted_key}.md topics/{slug}.md ...
```

Tell the user if the existing resonance is **stale**: it has no `generated`
line, its `by: resonate/<version>` is older than the newest **Conventions**
entry below, or its `at` is older than the `at` of any of its topics. If only
the conventions are stale, conform it first in its own commit, as
`/synthesize` does: append **Conform only** instructions naming the newer
Conventions entries, and commit as `Conform: {topics} to resonate@{version}`.

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
  - `{review_log}` — `.commonplace/skills/resonate/{sorted_key}.md`
  - `{date}` — today as YYYY-MM-DD
  - `{working_dir}` — absolute path to the repository root
  - `{version}` — this plugin's release, from step 1

Wait for the subagent to complete.

### 4. Review

**Present the subagent's summary to the user.** Do not re-read the artefact.
Wait for explicit approval before committing.

You haven't read the distillations, which makes you the right test: list
every term, name, or reference in the summary you couldn't explain from the
summary alone. If the list isn't empty, send it back — continue the subagent
if you can, otherwise spawn a revision subagent with the list and the
artefact path. Don't rewrite the lines yourself; you'd be putting a guess into
the record.

If the user requests changes, spawn a revision subagent or make small edits
directly.

**What the user says in review is a source.** A correction or addition made
here is recorded where the review happened, never deferred to a journal.
Before revising, append it verbatim to the review log,
`.commonplace/skills/resonate/{sorted_key}.md`, creating it headed
`# Review: {topics}` if missing:

```markdown
## <date> — Review
**<user>:**
> <their words, exactly as said>
```

The resonance cites it inline as *(<user>, in review, <date>)*, in plain
text, since topics don't link into `.commonplace/`. Pass the entry to the
revision subagent with the correction.

### 5. Commit

The user's approval is OKF's human review, so record it: set `verified` in
the resonance's frontmatter, beside `generated`, to
`{by: human:<user>, at: <now, e.g. 2026-10-01T14:00:00Z>}`. Only you write
this line, and only after approval — never the subagent.

```bash
commonplace git -- add topics/resonances/ .commonplace/skills/resonate/
commonplace git -- commit -m "Resonate: {topics}"
```

If a pre-commit hook reformats files, re-stage and retry.

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

## Conventions

What each release changed about the artefact. An entry is named by the
plugin release that introduced it, and only a release that changed the
artefact gets one: add an entry only for changes a reader would notice —
each one makes every existing resonance stale.

- **0.13.0** — A resonance is an OKF v0.2 concept document with
  `type: Topic`, a `title` and one-sentence `description`, `generated`
  naming the release that wrote it, and `verified` naming who approved it. `source_distillations` point at the
  flat `topics/<slug>.md`, and `updated` is gone.
- **0.12.0** — Citations in the body are root-relative wikilinks,
  `[[/<source path without .md>]]`, with no date beside them. Frontmatter
  paths stay bare. Every cited path resolves.
- **0.10.0** — Crossings and tensions restate what each topic contributes and
  name the topics. The Most Live Question is a headline sentence. Revisions
  lines are one sentence.
- **0.9.0** — Only primitives are quoted. Attribution and citations are
  carried through from the distillations. *Stopped* threads are never read as
  resolved. The resonance has a Revisions section.

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
- Review log: `{review_log}`
- Date: {date}
- Plugin release: {version}

Your job is to read the distillations, find the interference patterns between
them, and write a resonance artefact. Do **not** commit — return a compact
summary when done.

**Commonplace CLI**

```bash
commonplace search -n 20 "<query>"
```

### Phase 1: Read the Distillations

Read each distillation in full:

- `topics/{slug}.md` for each slug

Take notes on:

- The key threads in each topic (especially the Most Pressing Thread)
- Any vocabulary, concepts, or concerns that recur across topics
- Any apparent contradictions between how the topics are framed

If `{output_path}` already exists, read it — this is an update run. Note what
has changed in the distillations since it was last written.

Read `{review_log}` too, if it exists. Each `## <date> — Review` entry is
the user's own words from reviewing an earlier run: full evidence, which you
cite inline as *(<speaker>, in review, <date>)*, in plain text, and keep
honouring on update runs. Never edit the log; the calling agent appends to it.

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

Distillations attribute claims to speakers and cite `[[/<source path>]]`: a
root-relative wikilink, the path without `.md`. Carry both through, and cite
anything new you quote the same way. A distillation under an older convention
may still cite `(<date>, <path>)`; rewrite it as the plain wikilink. Where a
date is the point, it goes in the sentence or as `[<date>](/<path>.md)`. A crossing between two topics is a different and much
weaker thing if the two passages turn out to be an assistant's phrasing in
both places rather than the user's own.

### Phase 3: Write the Resonance

Write to: `{output_path}`

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

`description` says what ground the topics share or contest, not where the
reading has got to, so it holds from run to run. Write `generated` every
time you write the file. Never write `verified`:
that records the user's approval, which the calling agent adds after review.

Resonances update in place, so the Revisions section is the only in-band
record that this reading moved. One sentence per run, appended, never
rewritten, saying what changed rather than which headings you touched. If
an existing resonance has no such section, add it and open with
`<date> — Revision tracking begins; entries above predate it.`

**Write to be read cold.** A resonance is written about distillations, which
were written about sources, so its shorthand is two steps from anything
concrete. The reader has read neither distillation.

- Each crossing and tension restates what each topic contributes. Not "both
  circle the same legibility problem" but what that problem is in each.
- Name the topics; never "the former" or "the first topic".
- Gloss one topic's vocabulary before using it about another.

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
  contradict the art's investment in opacity?") do.

- **Write to be read cold.** See Phase 3. Applies to the return summary too.

- **Short is better.** A resonance that tries to say everything says nothing.
  Three sharp crossings beat ten loose ones.

- **Carry attribution and citations through** from the distillations,
  including *(<speaker>, in review, <date>)* citations, which stay plain
  text: they point at a review recorded in skill state, which is never
  linked.

- **Check every citation resolves.** Before returning, confirm each cited
  `[[/<path>]]` exists as `<path>.md`. If one is missing, the file has
  usually moved: find it by name (`find chats journal notes -name '<basename>.md'`) and cite where it is now.

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
- **Most Live Question**: \<its headline, verbatim>

**This run changed**: \<the Revisions line, verbatim>

**Artefact written**: `{output_path}`

______________________________________________________________________
