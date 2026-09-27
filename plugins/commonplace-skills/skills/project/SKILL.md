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
existing note **reviews and updates** it: the skill keeps its own three parts
current (the `Status:` line, `## History`, `## Next`), and proposes any change
to the rest of the note as a finding for the user to accept or reject.

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
`notes/projects/{slug}.md`. On an update run, check that the diff touches only
the Status line, History and Next, and that no existing History line changed;
History only grows. Check the First Next Action against the full Next list; if
the dependency reasoning looks off, flag it.

On an update run, go through the subagent's **review findings** one by one.
Each proposes a change to the user's own part of the note (tick an item, strike
it, correct a claim). The subagent hasn't applied them. Apply only the ones the
user accepts, and make exactly the edit proposed. As at every step, silence in
the record is not evidence something was done or dropped; a finding that rests
on it should be phrased as a question.

Wait for explicit approval before committing. If the user requests changes,
spawn a revision subagent or make small edits directly.

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

Chronological milestones and decisions, each citing a repo-relative source
path and date: "decided to X (2024-03-12, chats/claude/2024/03/2024-03-12-foo.md)".

## Next

Open questions, blockers, and next actions, one line each. The first is the
**First Next Action**: the one that unblocks the most others.
```

**Update run.** The note is the user's, often freeform. Review it, then
update the parts the skill keeps.

*New material* is any relevant search hit whose path the note doesn't already
cite, whatever its date. Don't filter by date: imports backfill old
conversations, and the note's citations are the record of what's been read.

*Review* the rest of the note against the record, and list what's changed:

- an open item (checkbox, todo line, plan) that a source shows done or
  explicitly set aside
- a claim or premise a later source contradicts
- a stated status or plan that the record has moved past

Don't edit these lines. Return each as a finding: the line verbatim, the
proposed edit, and the source. Where the only evidence is silence, phrase the
finding as a question ("no mention since 2025-03; still live?").

*Update* the parts the skill keeps:

- **`Status:`** line: rewrite it in place.
- **`## History`**: append the new material's milestones, cited as above.
  Never edit or remove existing History lines; the trajectory stays.
- **`## Next`**: rewrite it in place from the current state, then run the
  critique below.

If the note has none of these, as with a note the user started by hand,
add them once at the end, in the order of the new-note template. On later
runs, update them where they are.

If there's no new material and no finding, write nothing and say so.

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

**Review findings** (update runs only; omit if none):

- `{line, verbatim}` → {proposed edit, or a question}. Source: {path}.

**Note written**: `notes/projects/{slug}.md` ({new / updated / unchanged}),
{N} new sources.

______________________________________________________________________
