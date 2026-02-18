---
name: project
description: Extract a project artefact from the commonplace
argument-hint: <sketch or slug>
---

# Extract a Project

You are extracting a project artefact from a commonplace repository. The
argument is a sketch — it can be a slug (`commonplace`), a rough name
(`interviewing counter cultural luminaries`), or a short description. Use it
as a search seed.

The heavy work runs in a subagent. You handle slug derivation, review, and
commit.

## Prerequisites

The commonplace must have an index. If search returns errors, ask the user to
run `commonplace index` first.

## Workflow

### 1. Derive the Slug

Convert the sketch to a kebab-case slug. If ambiguous, confirm with the user.

Check whether `projects/{slug}/project.md` already exists — if so, this is an
update run.

### 2. Spawn the Extraction Subagent

Use the **Task tool** to spawn a `general-purpose` subagent:

- `description`: `"Extract project: {sketch}"`
- `subagent_type`: `"general-purpose"`
- `prompt`: Use the **Subagent Prompt Template** below, substituting:
  - `{sketch}` — the user's original sketch
  - `{slug}` — the derived slug
  - `{date}` — today as YYYY-MM-DD
  - `{working_dir}` — absolute path to the repository root

Wait for the subagent to complete.

### 3. Review

Present the subagent's summary to the user. Do not re-read the artefact file.
Wait for explicit approval before committing.

If the user requests changes, spawn a revision subagent or make small edits
directly.

### 4. Commit

```bash
commonplace git -- add projects/{slug}/
commonplace git -- commit -m "Extract project: {sketch}"
```

If a pre-commit hook reformats files, re-stage and retry.

Then re-index:

```bash
commonplace index
```

______________________________________________________________________

## Subagent Prompt Template

______________________________________________________________________

You are extracting a project artefact from a commonplace repository.

**Context**

- Repository root: `{working_dir}`
- Sketch: {sketch}
- Slug: {slug}
- Date: {date}

Your job is to find all material related to this project and write
`projects/{slug}/project.md`. Do **not** commit — return a compact review
summary when done.

**Commonplace CLI**

```bash
commonplace search -n 30 "<query>"
```

### Phase 1: Check for Prior Work

Check whether `projects/{slug}/project.md` already exists. If so, read it —
this is an update run (see Incremental Mode below).

### Phase 2: Search

Use the sketch to generate 3-5 search queries — expand abbreviations, try
synonyms, try related concepts:

```bash
commonplace search -n 30 "<query derived from sketch>"
```

Search for both the project's subject matter and action signals around it:
planning, progress, blockers, decisions, completions. Journal entries often
contain the richest project material — search them directly if they're
underrepresented in results.

Also search for status signals:

```bash
commonplace search -n 20 "{sketch} finished"
commonplace search -n 20 "{sketch} abandoned"
commonplace search -n 20 "{sketch} blocked"
```

**If search returns very little or nothing**, this is a stub project — the
user has a sketch but it hasn't materialised in the commonplace yet. Proceed
to Phase 3 with what you have; mark status as `speculative` and note the
thinness honestly.

### Phase 3: Determine Status

Based on the most recent signals, infer project status:

- **active**: recent mentions, ongoing work, open next steps
- **paused**: was active, no recent signals, no clear conclusion
- **complete**: explicit completion signals, shipped/finished language
- **abandoned**: explicit abandonment, or long silence after active period
- **speculative**: little or no material found; project exists as a sketch only

### Phase 4: Write the Artefact

Write to: `projects/{slug}/project.md`

```markdown
---
kind: project
status: active | paused | complete | abandoned | speculative
updated: <YYYY-MM-DD>
---

# Project: <name>

## What
One sentence. What is this project?

## History
Chronological milestones, decisions, and key moments. Cite dates and sources.
Be specific — "decided to X on YYYY-MM-DD" beats "at some point considered X".

## Current State
Where things stand as of {date}. What has been done, what hasn't.
For speculative projects: note that this is a sketch with little prior
material, and describe what the sketch implies.

## Threads
Open questions, blockers, and next actions.

### Most Pressing Thread
The single most important thing to address or decide next.
```

**For update runs:** revise each section to reflect new material. Be specific
about what changed. Update `status` if it has shifted. Update `updated`.

### Incremental Mode

When `projects/{slug}/project.md` already exists:

1. Read the existing artefact.
1. Search for material dated after the artefact's `updated` date.
1. Update the artefact in place — append to History, revise Current State and
   Threads. Update `updated` and `status` if needed.

Git tracks the full history. The prior state is always recoverable.

### Return Value

Return **only** this compact summary:

______________________________________________________________________

**Status**: {status}

**What**: {one sentence}

**History**: {2-3 sentence summary of key milestones}

**Current state**: {1-2 sentences}

**Threads**:

- {Thread}: {one sentence}
- *(repeat)*
- **Most Pressing Thread**: {thread} — {one sentence rationale}

**Artefact written**: `projects/{slug}/project.md`

______________________________________________________________________
