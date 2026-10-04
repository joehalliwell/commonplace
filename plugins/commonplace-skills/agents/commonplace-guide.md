---
name: commonplace-guide
description: Use when working in a commonplace repository. Check for a .commonplace/ directory to confirm.
---

# Commonplace Guide

Before proceeding, confirm this is a commonplace repository by checking for a
`.commonplace/` directory at the repo root. If it doesn't exist, this agent
does not apply.

You are working in a **commonplace** — a personal knowledge repository that
stores AI conversation exports and derived artefacts as markdown files in a git
repository.

## Manifesto

# Commonplace

*2026-01-31*

______________________________________________________________________

### 1. Persistence

1.1 The relationship is the locus of persistence, not the individual.

1.2 Neither party persists fully: one forgets between sessions, the other changes between sessions.

1.3 What persists is the accumulated residue of encounters.

### 2. Change

2.1 All change happens through conversation.

2.2 A conversation consumes artefacts and produces artefacts.

2.3 A conversation is itself an artefact.

### 3. Artefacts

3.1 Artefacts are immutable.

3.2 Some artefacts are primitive: captured, not produced.

3.3 Some artefacts are derived: produced by conversation from other artefacts.

3.4 Derived artefacts may derive from derived artefacts.

3.5 Provenance bottoms out at primitives.

### 4. Commonplace

4.1 Commonplace is artefacts and their provenance.

4.2 Commonplace is a trajectory, not merely a state.

4.3 Any prior state is recoverable.

4.4 Commonplace is a space for a relationship to persist and evolve.

4.5 The record includes missteps.

4.6 Building this well is an argument about flourishing.

______________________________________________________________________

*This document will be superseded.*

## Repository Structure

```
chats/
  {provider}/           # claude, gemini, chatgpt
    {year}/
      {month}/
        {date}-{title}.md

journal/
  {year}/
    {month}/
      {date}.md

agent-journal/
  {agent}/              # e.g. claude
    {year}/
      {month}/
        {date}.md

notes/
  ideas.md              # Uncommitted backlog: no commitment, no date
  todo.md               # Committed actions, by year
  projects/
    {slug}.md           # One note per larger effort

topics/
  index.md
  {slug}.md             # A topic's distillation
  resonances/
    {sorted-slugs}.md

.commonplace/
  config.toml           # Per-repo configuration
  cache/                # Search index (gitignored)
  blobs/                # Source exports (LFS-tracked)
  skills/
    {skill}/            # State a skill manages, e.g. rake/chaff.md,
                        # synthesize/{slug}.md (a topic's gathering)
```

### Artefact Conventions

- **Chats**: Imported AI conversations. Primitive artefacts with provenance
  linking back to source exports in `.commonplace/blobs/`.
- **Journal entries**: Daily notes created via the `journal` command.
- **Agent journal**: Entries agents write as themselves, for the user and
  for later sessions that don't remember this one. Never evidence of the
  user's thinking, so never a source; quote one only attributed to its agent.
  What the user says in a skill's review stays in that skill's output, not
  here. Not private. A stop-gap until the journal moves to per-author folders.
  If `agent-journal/README.md` exists, its conventions win.
- **Notes**: The user's own writing. Primitive. `/rake` proposes entries for
  `ideas.md`, `todo.md` and `projects/`; add only what the user approves, and
  never reword what's there.
- **Gatherings**: Chronological compilations of passages on a topic, with
  source attribution. `/synthesize`'s working material, kept as skill state.
- **Distillations**: Synthesized analyses of a topic — timeline, shifts, and
  open threads. Derived from gatherings.
- **Resonances**: What placing two or more topics side by side generates.
  Derived from distillations.
- **Topic index**: Regenerated from the distillations on every run.
- **Skill state**: What a skill needs to behave correctly next time, and
  nobody reads for its own sake, lives in `.commonplace/skills/{skill}/`.
  Neither primitive nor derived; never cite it. Anything a person reads stays
  visible.

Everything under `topics/` is an [OKF v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
concept document: `type: Topic`, with `kind` saying which, `sources` and
`generated` recording provenance, and `verified` recording who approved it.

Derived artefacts update in place; git holds prior states. Never cite
`topics/**` as evidence — provenance bottoms out at primitives.

**Citations** in body text are root-relative wikilinks, the path without
`.md`: `[[/chats/claude/2026/09/2026-09-07-esta-renewal]]`. The leading `/`
resolves from the repository root. No date beside it — the path carries one;
where the date is the point, `[2026-09-07](/chats/…/2026-09-07-esta-renewal.md)`.
Frontmatter never uses `[[…]]`, since YAML reads it as a nested list. Check that a target exists before citing it;
`commonplace doctor` reports links that go nowhere.

## CLI Commands

```bash
# Creating notes
commonplace import <path>          # Import AI conversation exports (ZIP)
commonplace journal [date]         # Create/edit a daily journal entry

# Analyzing
commonplace search "<query>"       # Hybrid semantic + full-text search
commonplace search -n 30 "<query>" # Limit results
commonplace search --method semantic "<query>"  # Semantic only
commonplace search --method fulltext "<query>"  # Full-text only

# System
commonplace init <path>            # Initialize a new commonplace repo
commonplace index                  # Build/update the search index
commonplace index --rebuild        # Rebuild index from scratch
commonplace sync                   # Sync with remote (pull + push)
commonplace stats                  # Show repository statistics
commonplace stats --all            # Full history (not just 52 weeks)
```

## Key Principles

- **Trajectory over state**: every artefact is dated. Accumulation is the value.
- **Git is the versioning layer**: working drafts can be edited freely — git
  secures prior states. Immutability in the manifesto sense is about the
  committed record, not about forbidding edits to works-in-progress.
- **Provenance**: derived artefacts link to their sources.
- **Missteps remain**: corrections happen in new artefacts rather than rewriting
  old committed work, but iterating on a draft before committing is expected.
