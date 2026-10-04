---
name: project
description: Draft a project note, or review and update an existing one, from the commonplace
argument-hint: <sketch or slug>
---

# Draft a Project Note

You are drafting or updating one project note, `notes/projects/{slug}.md`, in
a commonplace repository. The argument is a sketch: a slug (`commonplace`), a
rough name (`interviewing counter cultural luminaries`), or a short
description. Use it as a search seed. `/rake` is the usual way a project gets
here.

A project note is the **user's own note**, not a derived artefact. You draft
it from the record; the user owns it afterwards. Running `/project` on an
existing note **reviews and updates** it in place. The user approves the diff
before commit, and git holds every prior state.

The heavy work runs in a subagent. You handle slug derivation, review, and
commit.

## Prerequisites

The commonplace must have an index. If search returns errors, ask the user to
run `commonplace index` first.

## Workflow

### 1. Derive the Slug

Convert the sketch to a kebab-case slug. If ambiguous, confirm with the user.
Check `notes/projects/` for an existing note under this or a similar name; if
one exists, this is an update run on that file.

### 2. Spawn the Drafting Subagent

Use the **Task tool** to spawn a `general-purpose` subagent:

- `description`: `"Project note: {sketch}"`
- `subagent_type`: `"general-purpose"`
- `prompt`: Use the **Subagent Prompt Template** below, substituting:
  - `{sketch}` — the user's original sketch
  - `{slug}` — the derived slug
  - `{date}` — today as YYYY-MM-DD
  - `{working_dir}` — absolute path to the repository root

Wait for the subagent to complete.

### 3. Review

Present the subagent's summary, then show the diff of
`notes/projects/{slug}.md`. On an update run, check that every edit outside
Status, History and Next appears in the summary's Edits list with a source, and
that no existing History line changed; History only grows. Check the First
Next Action against the full Next list; if the dependency reasoning looks off,
flag it. Put the summary's Questions to the user.

Wait for explicit approval before committing. If the user rejects an edit,
revert that hunk (`commonplace git -- checkout -p notes/projects/{slug}.md`) or
make the correction directly.

### 4. Commit

If `notes/projects/index.md` exists, add or update the project's line there,
following the file's own sections and style. Don't touch other entries.

```bash
commonplace git -- add notes/projects/
commonplace git -- commit -m "Project note: {sketch}"
```

If a pre-commit hook reformats files, re-stage and retry.

Then re-index:

```bash
commonplace index
```

### 5. Agent Journal (optional)

This step is yours. What came up with the user belongs in this run's output,
recorded as the review step says; don't move or repeat it here. If what's
left (how the work went, a mistake of yours or a subagent's, what you'd do
differently) is worth a later session knowing, or you want to say something,
write it in
`agent-journal/{agent}/{yyyy}/{mm}/{yyyy-mm-dd}.md`, where `{agent}` names
you, e.g. `claude`. If nothing comes to mind, skip it.

If `agent-journal/README.md` exists, read it first. Otherwise: the entry is
yours, not the user's; they may read it; later sessions won't remember this
one, so write it to be read cold. Append if today's file exists; head a new
one like the user's journal, e.g. `# Thursday, October 1 2026`.

Commit it on its own and tell the user its path:

```bash
commonplace git -- add agent-journal/
commonplace git -- commit -m "Agent journal: {agent}"
```

______________________________________________________________________

## Subagent Prompt Template

______________________________________________________________________

You are drafting a project note in a commonplace repository.

**Context**

- Repository root: `{working_dir}`
- Sketch: {sketch}
- Slug: {slug}
- Date: {date}

Your job is to find all material related to this project and write or update
`notes/projects/{slug}.md`. Do **not** commit; return a compact review summary
when done.

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

**Cite primitives only.** Sources are `chats/`, `journal/`, `notes/`. Never
cite `topics/**`: those are derived, and a distillation's reading is not
evidence. If a distillation points you at something, follow its citation and
cite the primitive.

**Cite with root-relative wikilinks**: `[[/` + the repo-relative path without
`.md` + `]]`, e.g. `[[/journal/2026/08/2026-08-28]]`. Before returning, confirm
each cited path exists as `<path>.md`; if one is missing, find it by name
(`find chats journal notes -name '<basename>.md'`) and cite where it is now.
Leave the user's existing citations alone unless they go nowhere; report
those under Edits.

**Attribute.** Most sources are conversations with an assistant. The Why and
every History entry about intent must rest on the user's words, or on an
assistant's suggestion the user took up. Say who said it.

**If search returns very little**, the project is a sketch that hasn't
materialised in the commonplace yet. Write a short note that says so; don't
pad it.

### Phase 3: Status

Use the status words from `notes/projects/index.md` if it exists. Whatever
the vocabulary:

- **Silence is not abandonment.** A project going quiet in the record may be
  paused, done offline, or merely unrecorded. Call it abandoned or dropped
  only if the user said so in so many words; otherwise say when it was last
  touched and that you can't tell.
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
cite, whatever its date. Don't filter by date: imports backfill old
conversations, and the note's citations are the record of what's been read.

*Review* the rest of the note against the record, and edit it where a source
shows it's out of date:

- tick or strike an open item (checkbox, todo line, plan) that a source shows
  done or explicitly set aside
- correct a claim or premise a later source contradicts
- update a stated status or plan that the record has moved past

Make the smallest edit that fixes the line, in the note's own style, and list
each one in your return value with its source. Where the only evidence is
silence, don't edit: silence is not evidence something was done or dropped.
Return it as a question instead ("no mention since 2025-03; still live?").

*Update* the three parts the skill keeps:

- **`Status:`** line: rewrite it in place.
- **`## History`**: append the new material's milestones, cited as above.
  Never edit or remove existing History lines; the trajectory stays.
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
