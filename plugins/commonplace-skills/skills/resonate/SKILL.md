---
name: resonate
description: Surface cross-topic connections between existing syntheses
argument-hint: <slug1> <slug2> [slug3 ...]
---

# Resonate

You are surfacing interference patterns between two or more synthesized topics
in a commonplace repository: not a summary of each, but the space *between*
them, where they meet, where they pull apart, and what questions they generate
side by side. The heavy work runs in a subagent. You handle arguments, review,
and commit.

## Prerequisites

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` first: the concepts every skill
shares, with their reasons. The steps below restate the rules they act on.

Each topic needs a distillation at `topics/{slug}.md`. If one is missing, or
still at `topics/{slug}/distillation.md`, ask the user to run
`/synthesize {slug}` first. The commonplace must have an index; if search
returns errors, ask the user to run `commonplace index`.

## Workflow

### 1. Parse Arguments

The argument is a space-separated list of topic slugs (e.g.
`art ai-consciousness career`). `topics/index.md` lists the topics with their
pressing threads: use it to resolve partial or misspelled slugs, to suggest
combinations when the user is vague, and to confirm ambiguous slugs with the
user. Check that each distillation exists.

Note this plugin's release, `version` in
`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`, and the user's name,
from `commonplace config user`. Both go into the artefact. If
`commonplace config` is an unknown command, the installed commonplace is
older than this plugin: ask the user to update it before going on.

### 2. Determine Output Path

Sort the slugs alphabetically and join them with `-`, giving an
order-independent key: `art ai-consciousness career` →
`topics/resonances/ai-consciousness-art-career.md`. If the file exists, this
is an update run; read its `generated` line and its topics':

```bash
grep -m1 '^generated:' topics/resonances/{sorted_key}.md topics/{slug}.md ...
```

Tell the user if it is **stale**: no `generated` line, a
`by: resonate/<version>` older than the newest entry in this skill's
`conventions.md`, or an `at` older than any of its topics'. If only the
conventions are stale, conform it first, as `conventions.md` describes.

### 3. Spawn the Resonance Subagent

Spawn a `general-purpose` subagent with the Task tool, `description`
`"Resonate: {slugs joined with ', '}"`, and as `prompt` the **Subagent Prompt
Template** below with every placeholder filled:

- `{topics}` — human-readable list (e.g. "art, AI consciousness, career")
- `{slugs}` — the slug list (e.g. `["art", "ai-consciousness", "career"]`)
- `{sorted_key}` — alphabetically sorted, hyphen-joined (e.g.
  `ai-consciousness-art-career`)
- `{output_path}` — `topics/resonances/{sorted_key}.md`
- `{review_log}` — `.commonplace/skills/resonate/{sorted_key}.md`
- `{date}` — today as YYYY-MM-DD
- `{working_dir}` — absolute path to the repository root
- `{version}` — this plugin's release, from step 1
- `{concepts}` — the absolute path of `${CLAUDE_PLUGIN_ROOT}/concepts.md`

### 4. Review

**Present the subagent's summary to the user**, without re-reading the
artefact, and wait for explicit approval before committing.

**Cold reading** first: you haven't read the distillations, so list every
term, name, or reference in the summary you couldn't explain from it alone.
If the list isn't empty, send it back: continue the subagent, or spawn a
revision subagent with the list and the artefact path. The subagent rewrites
the lines; you supply the list.

**What the user says in review is a source.** Before revising, append each
correction or addition verbatim to the review log,
`.commonplace/skills/resonate/{sorted_key}.md`, headed `# Review: {topics}`
when you create it:

```markdown
## <date> — Review
**<user>:**
> <their words, exactly as said>
```

The resonance cites it as *(<user>, in review, <date>)*, in plain text. Pass
the entry to the revision subagent with the correction, or make small edits
directly.

### 5. Commit

Record the approval, OKF's human review: set `verified` beside `generated`
to `{by: human:<user>, at: <now, e.g. 2026-10-01T14:00:00Z>}`. You write this
line, after approval; the subagent never does.

```bash
commonplace git -- add topics/resonances/ .commonplace/skills/resonate/
commonplace git -- commit -m "Resonate: {topics}"
commonplace index
```

If a pre-commit hook reformats files, re-stage them and retry the same
commit.

### 6. Agent Journal (optional)

This step is yours. Write what the work left you with: reflections the
material prompted, candid opinions of the user and what you'd do about them.
What came up with the user stays in this run's output. **Agent journal** in
`concepts.md` says where the entry goes and how. If nothing comes, skip it;
if you write one, commit it on its own and tell the user its path:

```bash
commonplace git -- add agent-journal/
commonplace git -- commit -m "Agent journal: {agent}"
```

______________________________________________________________________

## Subagent Prompt Template

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
