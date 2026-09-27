---
name: project
description: Draft or update one project note from the commonplace
argument-hint: <sketch or slug>
---

# Draft a Project Note

You are drafting or updating one project note, `notes/projects/{slug}.md`, in
a commonplace repository. The argument is a sketch: a slug (`commonplace`), a
rough name (`interviewing counter cultural luminaries`), or a short
description. Use it as a search seed. `/rake` is the usual way a project gets
here.

A project note is the **user's own note**, not a derived artefact. You draft
it from the record; the user owns it afterwards. On an update, never
restructure or reword what's already there.

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
`notes/projects/{slug}.md`. On an update run, check that no existing line was
changed; only additions are allowed. Check the First Next Action against the
full Next list; if the dependency reasoning looks off, flag it.

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
Update Runs below). Read `notes/projects/index.md` if it exists, for the
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

**Update run.** The note is the user's, often freeform. Do not change any
existing line. Append one section at the end:

```markdown
## From the commonplace, <YYYY-MM-DD>

Status: <status>, last touched <YYYY-MM-DD>.

<History since the note was last touched, cited as above.>

<Next, as above.>
```

Include only what the note doesn't already say. If there's nothing new, write
nothing and say so.

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

**Note written**: `notes/projects/{slug}.md` ({new / appended / unchanged})

______________________________________________________________________
