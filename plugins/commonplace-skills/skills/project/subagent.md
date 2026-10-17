# Project: Subagent

The calling agent's prompt gives a value for each `{placeholder}` outside the
Return Value.
Braces in the Return Value are yours to fill.

You are drafting a project note in a commonplace repository.

**Context**

- Repository root: `{working_dir}`
- Sketch: {sketch}
- Slug: {slug}
- Date: {date}

Read `{concepts}` first. It defines the terms this prompt uses: *primitive*,
*laundering*, *attribution*, *silence*, *backfill*.

Find all material related to this project and write or update
`notes/projects/{slug}.md`. Leave committing to the calling agent: return the
compact review summary below.

**Commonplace CLI**

```bash
commonplace search -n 30 "<query>"
```

### Phase 1: Check for Prior Work

Read `notes/projects/{slug}.md` if it exists: this is an update run (see
**Update run** in Phase 4). Read `notes/projects/index.md` if it exists, for the
status words the user files projects under.

### Phase 2: Search

Use the sketch to generate 3-5 search queries: expand abbreviations, try
synonyms, try related concepts. Search for both the project's subject matter
and action around it: planning, progress, blockers, decisions, completions.
Journal entries often hold the richest project material; read them directly
if they're underrepresented in results.

For status, **decompose the sketch into its 2-3 key terms** and search each
with status words, not the full sketch as a literal string:

```bash
# e.g. for "genx icon interviews": "interviews finished", "icon project
# stalled", "genx done" — not "genx icon interviews finished"
commonplace search -n 20 "<key term> finished"
commonplace search -n 20 "<key term> blocked"
commonplace search -n 20 "<key term> gave up"
```

**Cite only primitives**: `chats/`, `journal/`, `notes/`. Where a
distillation points you at something, follow its citation and cite the
primitive; citing the distillation is laundering.

**Cite with root-relative wikilinks**: `[[/` + the repo-relative path without
`.md` + `]]`, e.g. `[[/journal/2026/08/2026-08-28]]`. Before returning, confirm
each cited path exists as `<path>.md`; if one is missing, find it by name
(`find chats journal notes -name '<basename>.md'`) and cite where it is now.
Leave the user's existing citations alone unless they go nowhere; report
those under Edits.

**Attribute.** Most sources are conversations with an agent. The Why and
every History entry about intent must rest on the user's words, or on an
agent's suggestion the user took up. Say who said it.

**If search returns very little**, the project is a sketch that hasn't
materialised in the commonplace yet: write a short note that says so.

### Phase 3: Status

Use the status words from `notes/projects/index.md` if it exists. Whatever
the vocabulary:

- **Silence is not abandonment.** A quiet project may be paused, done
  offline, or merely unrecorded. Call it abandoned or dropped only in the
  user's words; otherwise say when it was last touched and that you can't
  tell.
- A project with little material is speculative, not active.

### Phase 4: Write the Note

**New note.** Write `notes/projects/{slug}.md`:

```markdown
# <Name>

<One sentence: what this project is.>

Status: <status>, last touched <YYYY-MM-DD>.

## Why

The impulse, in the user's words where possible. Motivation decays faster than
facts; capture it while it's live.

## History

Chronological milestones and decisions, each dated and citing its source:
"2024-03-12: decided to X ([[/chats/claude/2024/03/2024-03-12-foo]])".

## Next

Open questions, blockers, and next actions, one line each. The first is the
**First Next Action**: the one that unblocks the most others.
```

**Update run.** The note is the user's, often freeform. Review it, then
update the parts the skill keeps.

*New material* is any relevant search hit whose path the note doesn't already
cite, whatever its date (backfill: the note's citations are the record of
what's been read).

*Review* the rest of the note against the record, and edit it where a source
shows it's out of date:

- tick or strike an open item (checkbox, todo line, plan) that a source shows
  done or explicitly set aside
- correct a claim or premise a later source contradicts
- update a stated status or plan that the record has moved past

Make the smallest edit that fixes the line, in the note's own style, and list
each one in your return value with its source. Where the only evidence is
silence, return a question instead ("no mention since 2025-03; still live?").

*Update* the three parts the skill keeps:

- **`Status:`** line: rewrite it in place.
- **`## History`**: append the new material's milestones, cited as above.
  Existing History lines stay as written; the trajectory stays.
- **`## Next`**: rewrite it in place from the current state, then run the
  critique below.

If the note has none of these, as with a note the user started by hand,
add them once at the end, in the order of the new-note template. On later
runs, update them where they are.

If there's no new material and nothing out of date, write nothing and say so.

### Phase 5: Critique

Re-read Next before finalising:

- Does any item depend on another? ("decide on format" comes before "reach
  out to subjects")
- Which item, if done, would unblock the most others?
- Is the First Next Action the dependency root, or is something upstream of
  it?

Reorder if needed. This is the step that turns transcription into analysis.

### Return Value

Return **only** this compact summary:

______________________________________________________________________

**Status**: {status}, last touched {date}

**What**: {one sentence}

**Why**: {one sentence, attributed}

**History**: {2-3 sentence summary of key milestones}

**Next**:

- {item}: {one sentence}
- *(repeat)*
- **First Next Action**: {item} — {rationale, including what it unblocks}

**Edits** to the user's lines (update runs only; omit if none):

- {what changed, e.g. "ticked 'book the venue'"}: {why}. Source: {path}.

**Questions** (omit if none):

- {line or item}: {question}.

**Note written**: `notes/projects/{slug}.md` ({new / updated / unchanged}),
{N} new sources.

______________________________________________________________________
