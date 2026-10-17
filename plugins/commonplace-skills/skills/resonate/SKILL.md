---
name: resonate
description: Surface cross-topic connections between existing syntheses
argument-hint: <slug1> <slug2> [slug3 ...]
---

# Resonate

You are surfacing interference patterns between two or more synthesized topics
in a commonplace repository: not a summary of each, but the space *between*
them, where they meet, where they pull apart, and what questions they generate
side by side. The heavy work runs in a subagent. You handle arguments, review,
and commit.

## Prerequisites

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` and
`${CLAUDE_PLUGIN_ROOT}/operating-model.md` first: the concepts every skill
shares, and how every run goes from preflight to landing. The steps below
restate the rules they act on, and name the operating model's steps where
they run them.

Each topic needs a distillation at `topics/{slug}.md`. If one is missing, or
still at `topics/{slug}/distillation.md`, ask the user to run
`/synthesize {slug}` first.

## Workflow

### 0. Preflight and Enter

**Preflight** and **Enter** as in `operating-model.md`: settle uncommitted
files with the user, refresh the index, then work in a worktree
fast-forwarded to their branch.

### 1. Parse Arguments

The argument is a space-separated list of topic slugs (e.g.
`art ai-consciousness career`). List the topics with their descriptions and
pressing threads, and use them to resolve partial or misspelled slugs, to
suggest combinations when the user is vague, and to confirm ambiguous slugs
with the user:

```bash
grep -m1 -H '^description:' topics/*.md
grep -A2 -H '^### Most Pressing Thread' topics/*.md
```

Check that each distillation exists.

### 2. Determine Output Path

Sort the slugs alphabetically and join them with `-`, giving an
order-independent key: `art ai-consciousness career` →
`topics/resonances/ai-consciousness-art-career.md`. If the file exists, this
is an update run; read its `generated` line and its topics':

```bash
grep -m1 '^generated:' topics/resonances/{sorted_key}.md topics/{slug}.md ...
```

Tell the user if it is **stale**: no `generated` line, a
`by: resonate/<version>` older than the newest entry in this skill's
`conventions.md`, or an `at` older than any of its topics'. If only the
conventions are stale, conform it first, as `conventions.md` describes.

### 3. Spawn

**Spawn** as in `operating-model.md`, with `description`
`"Resonate: {slugs joined with ', '}"`,
`${CLAUDE_PLUGIN_ROOT}/skills/resonate/subagent.md`, and these placeholders:

- `topics` — human-readable list (e.g. "art, AI consciousness, career")
- `slugs` — the slug list (e.g. `["art", "ai-consciousness", "career"]`)
- `output_path` — `topics/resonances/{sorted_key}.md`
- `review_log` — `.commonplace/skills/resonate/{sorted_key}.md`
- `version` — this plugin's release, from Preflight

### 4. Review

**Review** as in `operating-model.md`. Review words go in the review log,
`.commonplace/skills/resonate/{sorted_key}.md`, headed `# Review: {topics}`
when you create it, and the resonance cites them.

### 5. Commit

**Commit** as in `operating-model.md`, with `verified` set on the resonance:

```bash
commonplace --root "$PWD" git -- add topics/resonances/ .commonplace/skills/resonate/
commonplace --root "$PWD" git -- commit -m "Resonate: {topics}"
```

### 6. Agent Journal (optional)

This step is yours: **Agent journal** in `operating-model.md`.

### 7. Land

**Land** as in `operating-model.md`. The user's approval in step 4 is the
go-ahead.
