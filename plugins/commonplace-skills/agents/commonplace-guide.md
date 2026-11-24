---
name: commonplace-guide
description: Use when working in a commonplace repository. Check for a .commonplace/ directory to confirm.
---

# Commonplace Guide

Before proceeding, confirm this is a commonplace repository by checking for a
`.commonplace/` directory at the repo root. If it doesn't exist, this agent
does not apply.

You are working in a **commonplace** — a personal knowledge repository that
stores AI conversations, notes, journal entries, marginalia and derived
artefacts as markdown files in a git repository.

## Manifesto

*2026-01-31, revised 2026-11-07*

Commonplace is a record of a person and the agents they think with. It endures as
they change. It consists of many conversations: some keep what happens, some
make something new, most do both. Together they form a graph no one can see
whole. Its shadow is a git repository. One day something will replace it, and we
hope it will be us.

*Floreamus.*

## Repository Structure

```
chats/
  {agent}/              # claude, claude-code, gemini, gemini-takeout, chatgpt
    {year}/
      {month}/
        {date}-{title}.md
  claude/tasks/         # claude.ai scheduled-task runs (older: chats/claude-tasks/)

journal/
  {year}/
    {month}/
      {date}.md

agent-journal/
  {agent}/              # the agent that ran a skill, e.g. claude-code
    {year}/
      {month}/
        {date}.md

memory/
  {agent}/              # Agent memory, mirrored by fetch

notes/
  ideas.md              # Uncommitted backlog: no commitment, no date
  todo.md               # Committed actions, by year
  keep/                 # Google Keep notes, mirrored by fetch
  projects/
    {slug}.md           # One note per larger effort

topics/
  {slug}.md             # A topic's distillation
  resonances/
    {sorted-slugs}.md

.commonplace/
  config.toml           # Per-repo configuration
  cache/                # Search index (gitignored)
  blobs/                # Captured wire archives and exports (plain git objects)
  marginalia/           # Per-note tags, links and commentary, mirroring note paths
  skills/
    {skill}/            # State a skill manages, e.g. rake/chaff.md,
                        # synthesize/{slug}.md (a topic's gathering)
```

### Artefact Conventions

`${CLAUDE_PLUGIN_ROOT}/concepts.md` defines these, with the rules every skill
shares: attribution, citations, review; `operating-model.md` beside it says
how a skill run goes, from preflight to landing. Read both before writing
anything in the repository.

- **Chats, journal, notes**: primitive, and the only sources. The journal and
  notes are the user's own writing: add only what the user approves, and
  never reword what's there. `notes/keep/` is a mirror: a source, never a place
  to file anything.
- **Agent memory** (`memory/`): an agent's paraphrase of the user; a
  lead to the originating passage, not the user's words.
- **Agent journal**: the writing of the agent that ran a skill. Never a
  source.
- **Distillations and resonances** (`topics/`): derived, and
  OKF v0.2 concept documents. Never a source.
- **Gatherings, chaff, review logs** (`.commonplace/skills/`): skill state.
  Never linked, and cited only as a review, in plain text.

Derived artefacts update in place; git holds prior states.

## CLI Commands

```bash
# Creating notes
commonplace fetch                  # Pull new conversations, memory and Keep notes
commonplace import <path>          # Import vendor exports or wire archives
commonplace journal [date]         # Create/edit a daily journal entry

# Analyzing
commonplace search "<query>"       # Hybrid semantic + keyword search
commonplace search -n 30 "<query>" # Limit results
commonplace search --method semantic "<query>"  # Semantic only
commonplace search --method keyword "<query>"   # Keyword (FTS5) only
commonplace search --tag <t> --not-tag <t> "<q>" # Filter by tag (--all ignores exclude_tags)
commonplace ls [folder]            # List a folder's notes with titles and descriptions
commonplace show <note>            # Everything known about a note (tags, links, commentary, index)
commonplace resolve <note>         # Resolve a wikilink name or glob to path(s)
commonplace stats                  # Activity heatmap and per-source counts (--all for full history)

# Annotating (writes to .commonplace/marginalia/)
commonplace tag <note> <tag...>    # Add tags to notes' marginalia
commonplace untag <note> <tag...>  # Remove tags from notes' marginalia
commonplace link <note> <target> [why...]  # Link a note to another note or span
commonplace unlink <note> <target>         # Remove links to a target

# System
commonplace init <path>            # Initialize a new commonplace repo
commonplace index                  # Build/update the search index (--rebuild from scratch)
commonplace sync                   # Commit and sync with remote (pull + push)
commonplace git <args...>          # Run git against the commonplace from anywhere
commonplace doctor                 # Restore scaffolding, re-attach marginalia, check links (--render replays blobs)
commonplace config [key]           # Print merged settings in effect
```

## Key Principles

- **Trajectory over state**: every artefact is dated. Accumulation is the value.
- **Git is the versioning layer**: working drafts can be edited freely — git
  secures prior states. Immutability in the manifesto sense is about the
  committed record, not about forbidding edits to works-in-progress.
- **Provenance**: derived artefacts link to their sources.
- **Missteps remain**: corrections happen in new artefacts rather than rewriting
  old committed work, but iterating on a draft before committing is expected.
