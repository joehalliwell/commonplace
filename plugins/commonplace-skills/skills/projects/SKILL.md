---
name: projects
description: Scan the commonplace for candidate projects and update the project index
---

# Scan for Projects

You are scanning a commonplace repository for project-like material — things
being built, written, pursued, or planned. The goal is orientation: surface
what projects exist (or may exist), note their apparent status, and update the
project index. No per-project artefacts are written here; use `/project` for
that.

The heavy scanning runs in a subagent. You handle review, extraction offers,
and the optional index commit.

## Prerequisites

The commonplace must have an index. If search returns errors, ask the user to
run `commonplace index` first.

## Workflow

### 1. Spawn the Scan Subagent

Use the **Task tool** to spawn a `general-purpose` subagent:

- `description`: `"Scan for projects"`
- `subagent_type`: `"general-purpose"`
- `prompt`: Use the **Subagent Prompt Template** below, substituting:
  - `{date}` — today as YYYY-MM-DD
  - `{working_dir}` — absolute path to the repository root

Wait for the subagent to complete.

### 2. Review and Offer Extraction

Present the subagent's candidate list to the user, structured as:

- **Index staleness**: how long since the last scan (compute from
  `projects/index.md` frontmatter `updated` date — e.g. "last scanned 47
  days ago"). Omit if no index exists yet.
- **Drift** (if index exists): projects whose status has changed since the
  last scan, and candidates that have since been extracted.
- **Extracted projects**: already have a `projects/{slug}/project.md` artefact
- **Candidate projects**: discovered in the material, not yet extracted
- **Thin signals**: weak evidence, may not be real projects

After presenting, explicitly ask: **"Shall I extract any of these? If so,
which ones?"** If the user says yes, run `/project` for each confirmed
candidate in-session — spawn the extraction subagent(s) directly rather than
handing back to the command line. Handle review and commit for each as per the
`/project` workflow.

### 3. Update the Index (optional)

If the user approves, write or update `projects/index.md` with the confirmed
picture, then commit:

```bash
commonplace git -- add projects/index.md
commonplace git -- commit -m "Update project index"
```

If a pre-commit hook reformats files, re-stage and retry.

Then re-index:

```bash
commonplace index
```

______________________________________________________________________

## Subagent Prompt Template

______________________________________________________________________

You are scanning a commonplace repository for project-like material.

**Context**

- Repository root: `{working_dir}`
- Date: {date}

Your job is to surface candidate projects — things being built, written,
pursued, or planned. Do not write per-project artefacts. Return a structured
candidate list; the calling agent handles everything else.

**Commonplace CLI**

```bash
commonplace search -n 30 "<query>"
commonplace stats
```

### Phase 1: Read Existing Projects

Check the `projects/` directory for already-extracted project artefacts:

```bash
# List projects/{slug}/project.md files
```

Read each one. Note slug, status, and `updated` date. These form the
"extracted projects" section of your return value.

Also read `projects/index.md` if it exists. Note its `updated` date — you
will compare this against the current project artefacts to detect drift.

### Phase 2: Detect Drift

If `projects/index.md` exists, compare its `updated` date against each
extracted project's `updated` date and status:

- Projects whose `updated` date is more recent than the index were modified
  after the last scan — flag them as **status may have changed**.
- Projects listed as Candidates in the index that now have a
  `projects/{slug}/project.md` artefact — flag them as **since extracted**.

This drift section is often the most useful output when the index is fresh.

### Phase 3: Scan for Signals

Search for action-oriented and commitment language. Run all of these.

**First-person signals** (Joe writing to AI):

```bash
commonplace search -n 30 "working on"
commonplace search -n 30 "I'm building"
commonplace search -n 30 "I want to make"
commonplace search -n 30 "plan to"
commonplace search -n 30 "I need to"
commonplace search -n 30 "I've been"
```

**Task-oriented signals** (AI responding, or notes/journal):

```bash
commonplace search -n 30 "next steps"
commonplace search -n 30 "action items"
commonplace search -n 30 "to do"
commonplace search -n 30 "the goal is"
commonplace search -n 30 "the plan is"
commonplace search -n 30 "next step"
commonplace search -n 30 "deadline"
commonplace search -n 30 "project"
```

Journal entries are especially rich — scan recent ones directly if search
results feel thin.

Also search for completion and abandonment signals:

```bash
commonplace search -n 20 "finished"
commonplace search -n 20 "abandoned"
commonplace search -n 20 "gave up"
commonplace search -n 20 "shipped"
```

### Phase 4: Cluster into Candidates

Group hits by apparent project. For each cluster, assess project-ness using
these signals — **named + explicit next action is stronger than five unnamed
mentions**:

| Signal                          | Weight   |
| ------------------------------- | -------- |
| Has a proper name or title      | Strong   |
| Has an explicit next action     | Strong   |
| Has a stated goal or motivation | Moderate |
| Multiple mentions across time   | Moderate |
| Action language without a name  | Weak     |
| Single mention only             | Weak     |

A named project with one clear next action is a strong candidate. A nameless
topic with five mentions is a thin signal. Don't use mention count as a proxy
for project-ness.

For each candidate:

- Infer a name and slug
- Estimate status: active / paused / complete / abandoned
- Note the date range of signals (earliest to most recent mention)
- Write a one-line description
- Note the strongest evidence (a brief quote or source path)

Exclude topics that are clearly intellectual/exploratory with no action
component — those belong in `/synthesize`.

### Return Value

Return **only** this structured list:

______________________________________________________________________

**Drift since last scan** (omit section if no prior index):

- {slug}: {what changed — e.g. "status active→paused" or "now extracted"}

**Extracted projects** (already have artefacts):

| Slug | Status | Updated | Description |
| ---- | ------ | ------- | ----------- |
| ...  | ...    | ...     | ...         |

**Candidate projects** (discovered, not yet extracted):

- **{name}** (`{slug}`) — {one-line description}. Status signal: {active /
  paused / complete / abandoned}. Evidence: {date range}, {brief quote or
  source}.

*(repeat)*

**Thin signals** (weak evidence, may not be real projects):

- {name}: {one-line rationale for inclusion}

______________________________________________________________________

______________________________________________________________________

## Index Format

`projects/index.md`

```markdown
---
kind: project-index
updated: <YYYY-MM-DD>
---

# Projects

## Active

- [{Project Name}](projects/{slug}/project.md) — {one-line description}.
  Updated: {YYYY-MM-DD}.

## Paused

- ...

## Complete

- ...

## Abandoned

- ...

## Candidates

Projects identified but not yet extracted.

- **{Project Name}** — {one-line description}. Run `/project {slug}` to
  extract.
```
