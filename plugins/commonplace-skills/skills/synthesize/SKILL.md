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

Get the lay of the land, and index *before* gathering rather than only after:

```bash
commonplace index
commonplace stats
```

A stale index silently omits the most recent chats — exactly the material most
likely to have moved a topic on. Indexing is incremental, so this is cheap
when nothing has changed.

Note this plugin's release, `version` in
`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`, and the user's name,
from `commonplace config user`. Both go into the artefacts. If
`commonplace config` is an unknown command, the installed commonplace is
older than this plugin: ask the user to update it before going on.

Check which existing topics are **stale** — last synthesized under older
conventions. Each topic records the release that wrote it:

```bash
grep -m1 '^generated:' topics/{slug}.md
```

A topic is stale if the version in `by: synthesize/<version>` is older than
the newest **Conventions** entry below, if it has no `generated` line, or if
it is still a folder (`topics/{slug}/distillation.md`), the layout before
0.13.0.

If no topic argument was provided, run broad searches to discover recurring
themes:

```bash
commonplace search -n 50 "<broad query>"
```

Seed those queries from the repository rather than from guesswork: the
provider and date spread in `commonplace stats`, the titles of recently
modified notes (`commonplace git -- log --oneline -20 --name-only`), and any
existing `topics/index.md` entries — a topic already synthesized is evidence
of what the user cares about, and its threads suggest what's adjacent.

Propose 3-5 candidate topics to the user, and list any stale ones. Wait for
confirmation before proceeding.

If a topic argument WAS provided, skip discovery and proceed directly to
step 2.

Refuse the slugs `index`, `log` and `resonances`: OKF reserves `index.md`
and `log.md`, and `topics/resonances/` is taken.

### 2. Spawn the Synthesis Subagent

If the topic already exists and is stale (step 1), conform it first — see
**Conforming a Stale Topic** below.

Use the **Task tool** to spawn a `general-purpose` subagent:

- `description`: `"Synthesize: {topic}"`
- `subagent_type`: `"general-purpose"`
- `prompt`: Use the **Subagent Prompt Template** section below, substituting
  all `{placeholders}`:
  - `{topic}` — the confirmed topic name (e.g. "memory and continuity")
  - `{slug}` — kebab-case slug (e.g. "memory-and-continuity")
  - `{date}` — today as YYYY-MM-DD
  - `{working_dir}` — absolute path to the repository root
  - `{version}` — this plugin's release, from step 1

Wait for the subagent to complete before continuing. It will return a compact
review summary and the paths of the written artefacts.

### 3. Review

**Present the subagent's summary to the user.** Do not re-read the artefact
files — the subagent already produced the summary in the required format.
Wait for the user to approve, request changes, or redirect. Do not proceed to
commit without explicit approval.

Three things are worth checking in the summary before you present it,
because all are invisible once committed:

- **Attributed claims.** If a Shift or Thread describes how the *user's*
  thinking changed, the summary should make clear that's whose thinking it
  was — not an assistant's framing the user never took up.
- **Overstated endings.** Language like "abandoned" or "gave up on" is a
  claim about intent. Chats stop for logistical reasons; if the subagent has
  read silence as a decision, flag it.
- **Cold reading.** You are the one reader in this pipeline who hasn't read
  the sources, so test it: list every term, name, or reference in the summary
  that you couldn't explain from the summary alone. If the list isn't empty,
  send it back — continue the subagent if you can, otherwise spawn a revision
  subagent with the list and the distillation path. Don't rewrite the lines
  yourself; you'd be putting a guess into the record.

If the user requests changes, either ask the subagent to revise (spawn
another subagent with the correction) or make small edits directly.

**What the user says in review is a source.** A correction or addition made
here — who someone is, what a passage meant, something the sources don't
say — is recorded where the review happened, never deferred to a journal
entry. Before revising, append it to the gathering verbatim:

```markdown
## <date> — Review
**<user>:**
> <their words, exactly as said>
```

It is full evidence: the distillation cites it inline as
*(<user>, in review, <date>)* — plain text, since topics don't link into
`.commonplace/` — and it can support a Shift or Thread like any other quote.
Pass the entry to the revision subagent with the correction.

If the subagent returned **Stopped — overlaps `{existing-slug}`** instead of
a summary, no artefacts were written. Put the choice to the user — extend the
existing topic, or fork this one anyway — and re-spawn with their answer.

### 4. Regenerate the Topic Index

Rewrite `topics/index.md` from scratch so the topic is discoverable by the
next run, by `/resonate`, and by the user. The index is a pure function of
the topics — never edit it by hand or patch single entries. It is an OKF
§8 index, so it has no frontmatter:

```markdown
# Topics

- [<title>]({slug}.md) - <description> (N sources, updated <YYYY-MM-DD>)
  - **Pressing**: <the Most Pressing Thread's headline sentence, verbatim>

# Resonances

- [Resonances](resonances/) - what placing two or more of these topics side by side generates, written by `/resonate`
```

One entry per `topics/*.md` other than `index.md`, alphabetical by slug.
Read only what the entry needs: `title`, `description`, the date of
`generated.at`, N from the `sources` list, and the bold headline under
`### Most Pressing Thread`. Where any of these is missing, write
`not recorded` (or the slug, for a missing title). Include the Resonances
section only if `topics/resonances/` exists.

Topics not yet conformed are still folders. List each
`topics/*/distillation.md` too, in the same order, as
`- [{slug}]({slug}/distillation.md) - (stale: pre-0.13.0)`, so that
conforming one topic doesn't drop the rest from the index.

### 5. Commit

The user's approval is OKF's human review, so record it: set `verified` in
the topic's frontmatter, beside `generated`, to
`{by: human:<user>, at: <now, e.g. 2026-10-01T14:00:00Z>}`. Only you write
this line, and only after approval — never the subagent.

Stage and commit using `commonplace git`:

```bash
commonplace git -- add topics/{slug}.md topics/index.md .commonplace/skills/synthesize/{slug}.md
commonplace git -- commit -m "Synthesize: {topic name}"
```

If a pre-commit hook (e.g. a formatter) modifies files, the commit will fail.
Re-stage the reformatted files and retry the same commit — this is expected
behaviour, not an error.

Then re-index so the new artefacts are searchable:

```bash
commonplace index
```

Resonances that include `{slug}` were written against the old distillation;
name them to the user (`grep -l '^  - {slug}$' topics/resonances/*.md`).

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

### Conforming a Stale Topic

Bring a stale topic up to date in its own commit before adding new material,
so `git show` on that commit is exactly what the upgrade changed. Spawn the
subagent as in step 2, appending to the prompt:

If a newer Conventions entry says conforming to it needs new material, as
0.14.0 does, skip the conform-only step: do a normal update run instead,
and its Revisions line names the release it conforms to.

> **Conform only.** Gather no new sources. Bring both artefacts into line with
> the rules in this prompt, paying particular attention to these changes:
> \<the Conventions entries newer than the topic's `generated.by`, or all of
> them>. Where a change depends on content — a gloss, a thread's status —
> re-read the cited passage rather than guessing. The Revisions line is
> `<date> — Conformed to synthesize@<version>; no new sources.`

A topic still in the folder layout moves first, with `git mv` so history
follows it:

```bash
mkdir -p .commonplace/skills/synthesize
commonplace git -- mv topics/{slug}/distillation.md topics/{slug}.md
commonplace git -- mv topics/{slug}/gathering.md .commonplace/skills/synthesize/{slug}.md
```

The gathering's `queries` and `sources` move into the topic's frontmatter,
the sources in their structured form, and the topic gains a `title` and a
`description`.

Then every link to the old paths is repointed: `[[/topics/{slug}/distillation]]`
becomes `[[/topics/{slug}]]`, and a resonance's `source_distillations` entry
becomes `topics/{slug}.md`. Find them with
`grep -rn 'topics/{slug}/' --include='*.md' .`. Under `topics/`, change the
link target and nothing else. Three exceptions:

- **Revisions lines are history.** A path there says where something was
  when the line was written, and repointing it can falsify the sentence. Make
  each such link a code span of the path as written (`[[/topics/ethics/gathering]]`
  becomes `` `topics/ethics/gathering` ``) and change nothing else.
- **Links to the gathering** become code spans too, wherever they are:
  gatherings are skill state, and topics never link into `.commonplace/`.
- **Links in `notes/` and `journal/`** are the user's: list them in your
  review and change them only if the user says so.

Review as in step 3, and stage the moved paths and every file you repointed.
Commit as `Conform: {topic name} to synthesize@{version}`. Run a normal
synthesis afterwards only if the user wants new material too.

## Conventions

What each release changed about the artefacts. An entry is named by the
plugin release that introduced it, and only a release that changed the
artefacts gets one: add an entry only for changes a reader would notice —
each one makes every existing topic stale.

- **0.14.0** — Gathering includes a mandatory grep pass over `journal/`,
  `notes/` and `chats/`, and the topic records its patterns in `patterns`
  beside `queries`; update runs repeat both. Conforming to this needs new
  material, so it is a normal update run, not a conform-only pass.
- **0.13.0** — A topic is an OKF v0.2 concept document at `topics/{slug}.md`,
  with `type: Topic`. Its frontmatter carries a `title` and a one-sentence
  `description` (which the index lists it by), `queries`, structured
  `sources` (each a `resource`, and no `author`),
  `generated` naming the release that wrote it, and `verified` naming who
  approved it. `resource` paths are root-relative, with a leading `/`.
  `updated` and `source_gathering` are gone. The gathering is skill state at
  `.commonplace/skills/synthesize/{slug}.md`. `topics/index.md` has no
  frontmatter, and lists `resonances/`.
- **0.12.0** — Citations in the body are root-relative wikilinks,
  `[[/<source path without .md>]]`, with no date beside them; a date that
  matters is written as `[<date>](/<source path>.md)`. Gathering entries
  name their source as `*[[/<path without .md>]]*`. Frontmatter paths stay
  bare. Every cited path resolves.
- **0.10.0** — Threads carry *closed* / *stopped* / *unclear* and a
  last-touched date. Each thread name is one sentence stating the question.
  Coinages are glossed in every thread entry that uses them. The Most Pressing
  Thread is a headline sentence plus at most one short paragraph. Revisions
  lines are one sentence.
- **0.9.0** — Every gathered quote carries its speaker. Only primitives are
  sources. Distillation claims cite `(<date>, <source path>)`. The gathering
  lists its `sources`. The distillation has a Revisions section.

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
- Plugin release: {version}

Your job is to check for prior work, gather sources, and write the gathering
and the topic's distillation. Do **not** commit — return a compact review
summary when done and the calling agent will handle review and commit.

**Commonplace CLI**

```bash
commonplace stats
commonplace search -n 30 "<query>"   # hybrid semantic + full-text
commonplace search -n 5 "<query>"
```

### Phase 1: Check for Prior Work

Before searching sources, check whether this topic has already been
distilled, by looking for its files:

- `topics/{slug}.md` — the distillation
- `.commonplace/skills/synthesize/{slug}.md` — the gathering

If prior artefacts exist, read them now — they establish existing coverage and
determine whether this is a first-run or an update (see Incremental Mode
below).

**Check for overlap with existing topics.** An exact slug match is not enough:
topics accrete, and nothing else stops `memory-and-continuity`, `continuity`
and `persistence` becoming three topics that gather the same chats and never
learn about each other. So:

```bash
ls topics/
```

Read `topics/index.md` if it exists, and the `queries` and `patterns` of any
`topics/*.md` whose slug or entry looks adjacent to `{slug}`. If a substantial part of
what you'd gather is already gathered elsewhere, **stop and say so in your
return value** rather than proceeding — name the overlapping topic and offer
the choice between extending it and forking a new one. Two thin overlapping
topics are worse than one thick one, and merging them later means reconciling
two Revisions histories by hand.

Proceed without asking when the overlap is incidental — shared vocabulary,
a handful of sources in common.

### Phase 2: Gather

Run at least 3-5 searches with different phrasings:

```bash
commonplace search -n 30 "<specific query>"
```

**Search strategy:** After initial searches, check coverage by source
directory (chats, journal, notes) — if any is unrepresented, run a targeted
query for it. Breadth of querying matters; there is no systematic way to know
what you missed.

**Then grep.** Search ranks short journal entries below long chats, so it
misses much of the journal. A keyword pass is mandatory, not a fallback:
grep for the topic's distinctive words, names (in every variant) and
coinages across all three directories:

```bash
grep -rliE '<pattern>' journal notes chats
```

Use case-insensitive extended regexes, and record every pattern you ran in
the topic's `patterns`, beside `queries`, so a later run can repeat it.

**Gather only from primitives.** Sources are `chats/`, `journal/`, `notes/` —
the captured record — plus the gathering's Review entries (below). Never quote `topics/**` into a gathering: distillations,
resonances and the topic index are *derived* artefacts, and prior runs commit
and re-index them, so they will surface in your search results alongside real
sources. Quoting one launders synthesis back into evidence, counts the same
claim twice, and breaks the provenance chain — every claim must bottom out at
something captured, not something previously concluded. Prior work on this
topic is read in Phase 1 to establish coverage; it is not a source.

**Triage before deep reading.** For topics with many hits (>15 sources), do a
triage pass first: skim each source (first ~100 lines or the section around
the search hit) and rank by relevance. Only do full reads of the top sources.
Use background subagents to parallelise reading of large files.

Read the sources that survive triage in full (use the Read tool). For each
relevant section:

- Note the date (from file path or frontmatter)
- Extract the relevant passage
- **Note who said it** — transcripts mark speakers with `## Human` /
  `## Claude` (or whatever names the serializer was configured with)
- Track the source path

Order all gathered material chronologically.

**Attribution is not optional.** A quote with no speaker is worse than no
quote: an assistant's speculative riff, gathered unattributed, comes back a
year later as evidence of how the user's own thinking evolved. Most sources
here are conversations *with* an assistant, so this is the default failure
mode, not an edge case. Every quote carries its speaker.

**Scope is relevance, not sensitivity.** This is the user's private record.
Gather whatever bears on the topic, however intimate, and leave out only
what is irrelevant. If you hold anything back, say so in your return value.

**Search for every name a person goes by.** Sources spell people
differently — nicknames, short forms, transliterations. Once you know the
variants, search and grep for each.

**Review entries are sources.** A gathering entry headed `## <date> — Review`
records what the user said in reviewing an earlier run. It is the user's own
words, captured, and counts as full evidence. Keep it on update runs, and
cite it inline as *(<speaker>, in review, <date>)*, in plain text.

### Phase 3: Write the Gathering

Write to: `.commonplace/skills/synthesize/{slug}.md`

The gathering is your working material, kept for the next run: nobody reads
it for its own sake, and the search index skips it. The queries and the
source list that a later run diffs against live in the topic's frontmatter
(Phase 4), so the gathering holds only the quotes.

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

## <date> — <title or context>
*[[/<repo-relative source path without .md>]]*

**<speaker>:**
> Relevant passage text...
```

Where a passage only makes sense as an exchange, quote both turns in order
rather than collapsing them into one attributed block.

**Cite with root-relative wikilinks** in the body: `[[/` + the repo-relative
path without `.md` + `]]`, e.g. `[[/journal/2014/08/2014-08-14]]`. The
leading `/` resolves from the repository root wherever the citing file sits.
Don't put a date beside it: `chats/` and `journal/` paths already carry one.
In the rare case the date itself is the point, make it the link text of a
markdown link instead: `[2014-08-14](/journal/2014/08/2014-08-14.md)`.
Frontmatter never uses `[[…]]`: it's YAML, and `[[…]]` parses there as a
nested list.

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

**Chats end for logistical reasons.** Context limits, session timeouts, an
interruption at the desk. The end of a transcript is not a conclusion, and a
line of thought going quiet is not evidence it was abandoned. Before calling
anything dropped:

- **Search for it resuming elsewhere.** Continuation in a *later, separate
  chat* is the normal shape here — the transcript boundary is an artefact of
  logistics, not a boundary of thought.
- **Distinguish closed from stopped.** *Closed*: explicitly resolved, or set
  aside in so many words. *Stopped*: the transcript simply ends, often
  mid-exchange or on an unanswered question. Say which you mean.
- **When you can't tell, say so.** "Last touched 2026-03-14, no visible
  resolution" is honest and useful. "Abandoned in March" is a fabrication
  about the user's intent.

The same caution applies to **Shifts**: an apparent change of mind is often
just a new chat that never picked up the old framing. A framing that stops
recurring may have been settled, superseded, or merely interrupted — and only
the first two are shifts.

**Write to be read cold.** You have just read every source; the reader has
not and will not. They are the user months from now, a later run,
`/resonate`, or a search hit — and the index splits text at about 1,000
characters, so a hit is often one thread entry with only its headings around
it.

- **Nothing points outside the text.** Not "this tension" or "the published
  argument" but "the tension between shipping and rewriting", "the March
  essay on attention".
- **Gloss coinages in every thread entry that uses them.** Vocabulary minted
  in a chat ("the archive move", "the two-drawer rule") gets a clause of
  explanation each time it appears in a new entry, not once per document.
- **Name the thread with the question itself.** Not **The opacity problem**
  but **Does making the work legible to an audience cost it the ambiguity
  that made it worth making?**
- **Short.** Detail belongs in Timeline and Shifts, with citations; a thread
  entry says what's open and the evidence either way.

**Cite claims to passages, not to the source list.** The frontmatter's
`sources` is provenance to files, which leaves a reader unable to check "the
framing shifted in March" without re-reading everything. OKF would key
per-claim footnotes to it; don't, because a search hit is one chunk, and a
footnote whose definition sits in another chunk tells the reader nothing.
Each substantive claim carries an inline `[[/<source path>]]`, as in Phase 3,
and where the claim is about who thought what, name the speaker too. Where
*when* matters, say it in the sentence ("in March 2024, …"). Provenance has to bottom out at a passage.

Write to: `topics/{slug}.md`

```markdown
---
type: Topic
kind: distillation
title: {topic}
description: <one sentence: what this topic covers>
queries:
  - "<search query 1>"
  - "<search query 2>"
patterns:
  - '<grep -iE pattern 1>'   # single-quoted, so backslashes survive YAML
  - '<grep -iE pattern 2>'
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
Open questions, unresolved tensions, areas for future exploration. Mark each
thread *closed*, *stopped*, or *unclear*, with the date it was last touched:

- **<The open question, as one sentence>** — *stopped*, last touched <date>.
  <What's unresolved, and the evidence either way.>

### Most Pressing Thread
**<One sentence naming its subject and stating the question.>**

<At most one short paragraph: why it matters now.>

## Revisions
- <YYYY-MM-DD> — <one sentence: what the distillation now says that it didn't>
```

This is an OKF v0.2 concept document: `type` is what makes it one, and the
other keys are OKF's provenance fields. `description` is what the index
lists the topic by: say what ground the topic covers, not where it has got
to, so it holds from run to run. Write it to be read cold, beside other
topics' descriptions. List every source you quoted in the
gathering, in its order. Sources carry no `author`: commonplace doesn't
assign its material to individuals, and a source's path already says
whether it is a chat, a journal entry or a note. Write `generated` every
time you write the file. Never write `verified`: that
records the user's approval, which the calling agent adds after review.

The Most Pressing Thread's headline is copied verbatim into
`topics/index.md`, beside other topics and with none of this document around
it. Write it to survive that.

**The Revisions section carries the trajectory.** Distillations are updated in
place, so without it every run silently overwrites the last and the only
record of how the reading changed is a diff nobody reads — invisible to the
search index, which sees the working tree alone. One sentence per run, saying
what the distillation now says that it didn't — not which headings changed:

- On a first run: `<date> — First distillation, N sources.`
- On an update: what new material arrived and what it changed. Name
  corrections explicitly — "March's reading of X as Y was wrong; the later
  chats show Z" — because a correction that silently replaces its predecessor
  erases the misstep, and the record is supposed to include missteps.
- If a run added sources but changed no conclusions, say that. It's a real
  finding: the reading held.

Newest entries at the bottom. Never rewrite or prune existing lines.

### Incremental Mode

When `topics/{slug}.md` already exists, this is an update run:

1. **Read the existing distillation** to understand current coverage, and
   the gathering if there is one.

1. **Search for new material** — re-run the `queries` and the grep
   `patterns` recorded in the topic's frontmatter, plus any new ones, and
   compare the hits against its `sources` list. Anything not already listed is new material,
   **whatever its date**. You don't need to re-read sources already on the
   list.

   Do not filter by "newer than the last run". Imports backfill: a fresh
   export or a fetch that reaches further back adds *old* conversations to
   the repository, and a date cutoff skips them silently. The `sources` list
   is the record of what has actually been read; diff against that.

1. **Update the gathering in place** — append new entries in chronological
   order.

1. **Update the distillation in place** — revise Timeline, Shifts, and
   Threads to reflect new material. Add the new `sources`, add any new
   `queries`, and rewrite `generated`. Leave `verified` alone; the calling
   agent updates it after review.

1. **Append a Revisions line** recording what this run changed. This is the
   only in-band record that the distillation moved.

If the existing distillation has no `## Revisions` section, it predates the
convention. Add the section and open it with a single line — e.g.
`<date> — Revision tracking begins; entries above predate it.` — then append
this run's line. Do not attempt to reconstruct earlier runs from git history,
and do not retro-attribute speakers in gathering entries you haven't
re-read: a guess in the record is worse than an acknowledged gap.

Git tracks the full history. The prior state is always recoverable.

### Guidelines

- **Attribute every quote.** Whose thought was this? See Phase 2.
- **Gather from primitives only.** Never cite `topics/**` as a source.
- **Interruption is not abandonment.** See Phase 4. Applies to both Threads
  and Shifts.
- **Quote generously** in gatherings — but scale quoting inversely with source
  count. 5 sources: quote everything relevant. 20 sources: quote turning points,
  summarise the rest.
- **Be specific** in distillations. Every substantive claim carries an inline
  `[[/<source path>]]` — provenance bottoms out at a passage, not a file.
- **Check every citation resolves.** Before returning, confirm each cited
  `[[/<path>]]` exists as `<path>.md`, and each `[<date>](/<path>.md)` and
  each `resource` as written. Files move (a re-import can rename a
  provider directory); if one is missing, find it by name
  (`find chats journal notes -name '<basename>.md'`) and cite where it is
  now. Never leave a link that goes nowhere.
- **Never link to the gathering**, or to anything under `.commonplace/`.
  It's skill state, which the link checker can't follow; cite its Review
  entries in plain text instead.
- **Name the threads**. The most valuable output is often what's unresolved.
- **Write to be read cold.** See Phase 4. Applies to the return summary too.
- **Don't over-synthesize**. If the material is thin, say so. A short
  distillation noting "only 2 sources, early exploration" is more honest than
  padding.
- **Trajectory over state**: each synthesis run is additive. Don't try to
  produce a "final" summary. The accumulation IS the value — now via git
  history rather than dated filenames.
- **Missteps remain**: if a prior distillation got something wrong, the new one
  corrects it in place — and names the correction in Revisions, so the misstep
  stays legible to a reader rather than only to `git log`.

### Return Value

If you stopped in Phase 1 on a substantial overlap, return only:

______________________________________________________________________

**Stopped — overlaps `{existing-slug}`**

- What that topic already covers: <one or two sentences>
- What `{slug}` would add that it doesn't: <one or two sentences>
- Recommendation: \<extend `{existing-slug}` / fork `{slug}` anyway>

______________________________________________________________________

Otherwise, when both artefacts are written, return **only** this compact
summary — do not print the file contents. The user reads only this before
approving the commit, so every line must make sense without the artefacts.

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
