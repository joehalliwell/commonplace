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

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` first: the concepts every skill
shares, with their reasons. The steps below restate the rules they act on.

The commonplace must have an index. If search returns errors, ask the user to
run `commonplace index` first.

## Workflow

### 1. Survey

Index before gathering, so the newest chats (the material most likely to
have moved a topic on) are searchable. Indexing is incremental and cheap:

```bash
commonplace index
commonplace stats
```

Note this plugin's release, `version` in
`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`, and the user's name,
from `commonplace config user`. Both go into the artefacts. If
`commonplace config` is an unknown command, the installed commonplace is
older than this plugin: ask the user to update it before going on.

A topic is **stale** if `by: synthesize/<version>` in its `generated` line
(`grep -m1 '^generated:' topics/{slug}.md`) is older than the newest entry in
this skill's `conventions.md`, if it has no `generated` line, or if it is
still a folder, `topics/{slug}/distillation.md`.

With no topic argument, discover candidates with broad searches
(`commonplace search -n 50 "<broad query>"`), seeded from the repository: the
agent and date spread in `commonplace stats`, recently modified notes
(`commonplace git -- log --oneline -20 --name-only`), and `topics/index.md`,
whose topics show what the user cares about and whose threads suggest what's
adjacent. Propose 3-5 candidates, list any stale topics, and wait for
confirmation. With a topic argument, go straight to step 2.

Refuse the slugs `index`, `log` and `resonances`: OKF reserves `index.md`
and `log.md`, and `topics/resonances/` is taken.

### 2. Spawn the Synthesis Subagent

A stale topic is conformed first: follow `conventions.md` in this skill's
directory.

Spawn a `general-purpose` subagent with the Task tool, `description`
`"Synthesize: {topic}"`, and as `prompt` the **Subagent Prompt Template**
below with every placeholder filled:

- `{topic}` — the confirmed topic name (e.g. "memory and continuity")
- `{slug}` — kebab-case slug (e.g. "memory-and-continuity")
- `{date}` — today as YYYY-MM-DD
- `{working_dir}` — absolute path to the repository root
- `{version}` — this plugin's release, from step 1
- `{concepts}` — the absolute path of `${CLAUDE_PLUGIN_ROOT}/concepts.md`

It returns a compact review summary and the paths it wrote.

### 3. Review

**Present the subagent's summary to the user**, without re-reading the
artefacts, and wait for explicit approval before committing. First check
three things that are invisible once committed:

- **Attribution.** A Shift or Thread about the *user's* thinking rests on the
  user's words, not an agent's framing the user never took up.
- **Silence.** "Abandoned" or "gave up on" claims intent; flag any ending
  the subagent read from silence.
- **Cold reading.** List every term, name, or reference in the summary you
  couldn't explain from the summary alone. If the list isn't empty, send it
  back: continue the subagent, or spawn a revision subagent with the list and
  the distillation path. The subagent rewrites the lines; you supply the
  list.

**What the user says in review is a source.** Before revising, append each
correction or addition to the gathering, verbatim:

```markdown
## <date> — Review
**<user>:**
> <their words, exactly as said>
```

The distillation cites it as *(<user>, in review, <date>)*, in plain text.
Pass the entry to the revision subagent with the correction, or make small
edits directly.

If the subagent returned **Stopped — overlaps `{existing-slug}`**, nothing was
written: put the choice (extend that topic, or fork this one) to the user,
and re-spawn with their answer.

### 4. Regenerate the Topic Index

Rewrite `topics/index.md` from scratch, as a pure function of the topics, so
the next run, `/resonate` and the user can find this one. It is an OKF §8
index, so it has no frontmatter:

```markdown
# Topics

- [<title>]({slug}.md) - <description> (N sources, updated <YYYY-MM-DD>)
  - **Pressing**: <the Most Pressing Thread's headline sentence, verbatim>

# Resonances

- [Resonances](resonances/) - what placing two or more of these topics side by side generates, written by `/resonate`
```

One entry per `topics/*.md` other than `index.md`, alphabetical by slug,
built from `title`, `description`, the date of `generated.at`, N from
`sources`, and the bold headline under `### Most Pressing Thread`. Write
`not recorded` for anything missing (the slug, for a missing title). Include
Resonances only if `topics/resonances/` exists. List each unconformed
`topics/*/distillation.md` too, in the same order, as
`- [{slug}]({slug}/distillation.md) - (stale: pre-0.13.0)`.

### 5. Commit

Record the approval, OKF's human review: set `verified` beside `generated`
to `{by: human:<user>, at: <now, e.g. 2026-10-01T14:00:00Z>}`. You write this
line, after approval; the subagent never does.

```bash
commonplace git -- add topics/{slug}.md topics/index.md .commonplace/skills/synthesize/{slug}.md
commonplace git -- commit -m "Synthesize: {topic name}"
commonplace index
```

If a pre-commit hook reformats files, re-stage them and retry the same
commit. Then name to the user the resonances written against the old
distillation (`grep -l '^  - {slug}$' topics/resonances/*.md`).

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
and `persistence` can become three topics gathering the same chats. Read
`topics/index.md` and the `queries` and `patterns` of any topic whose slug or
entry looks adjacent to `{slug}`. If a substantial part of what you'd gather
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
- Thread entries say what's open and the evidence either way; detail and
  citations live in Timeline and Shifts.

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
run to run, and is what the index lists it by. `sources` lists every source
the gathering quotes, in its order, each a bare `resource` (the path already
says what kind of source it is). Write `generated` every time you write the
file; `verified` is the calling agent's, added after review. The Most
Pressing Thread's headline is copied verbatim into `topics/index.md`, so it
must stand alone.

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
