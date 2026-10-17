---
name: synthesize
description: Discover and synthesize topics from the commonplace
argument-hint: '[topic]'
---

# Synthesize Topics

You are performing topic synthesis on a commonplace repository. The heavy work
(searching, reading, writing artefacts) runs in a subagent. You handle survey,
review, and commit.

## Prerequisites

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` and
`${CLAUDE_PLUGIN_ROOT}/operating-model.md` first: the concepts every skill
shares, and how every run goes from preflight to landing. The steps below
restate the rules they act on, and name the operating model's steps where
they run them.

## Workflow

### 0. Preflight and Enter

**Preflight** and **Enter** as in `operating-model.md`: settle uncommitted
files with the user, refresh the index, then work in a worktree
fast-forwarded to their branch.

### 1. Survey

A topic is **stale** if `by: synthesize/<version>` in its `generated` line
(`grep -m1 '^generated:' topics/{slug}.md`) is older than the newest entry in
this skill's `conventions.md`, if it has no `generated` line, or if it is
still a folder, `topics/{slug}/distillation.md`.

With no topic argument, discover candidates with broad searches
(`commonplace search -n 50 "<broad query>"`), seeded from the repository: the
agent and date spread in `commonplace stats`, recently modified notes
(`commonplace git -- log --oneline -20 --name-only`), and `topics/index.md`,
whose topics show what the user cares about and whose threads suggest what's
adjacent. Propose 3-5 candidates, list any stale topics, and wait for
confirmation. With a topic argument, go straight to step 2.

Refuse the slugs `index`, `log` and `resonances`: OKF reserves `index.md`
and `log.md`, and `topics/resonances/` is taken.

### 2. Spawn

A stale topic is conformed first: follow `conventions.md` in this skill's
directory.

**Spawn** as in `operating-model.md`, with `description`
`"Synthesize: {topic}"`, `${CLAUDE_PLUGIN_ROOT}/skills/synthesize/subagent.md`,
and these placeholders:

- `topic` — the confirmed topic name (e.g. "memory and continuity")
- `slug` — kebab-case slug (e.g. "memory-and-continuity")
- `version` — this plugin's release, from Preflight

### 3. Review

**Review** as in `operating-model.md`, with two checks of this skill's own,
since both are invisible once committed:

- **Attribution.** A Shift or Thread about the *user's* thinking rests on the
  user's words, not an agent's framing the user never took up.
- **Silence.** "Abandoned" or "gave up on" claims intent; flag any ending
  the subagent read from silence.

Review words go in the gathering, `.commonplace/skills/synthesize/{slug}.md`,
and the distillation cites them.

If the subagent returned **Stopped — overlaps `{existing-slug}`**, nothing was
written: put the choice (extend that topic, or fork this one) to the user,
and re-spawn with their answer.

### 4. Regenerate the Topic Index

Rewrite `topics/index.md` from scratch, as a pure function of the topics, so
the next run, `/resonate` and the user can find this one. It is an OKF §8
index, so it has no frontmatter:

```markdown
# Topics

- [<title>]({slug}.md) - <description> (N sources, updated <YYYY-MM-DD>)
  - **Pressing**: <the Most Pressing Thread's headline sentence, verbatim>

# Resonances

- [Resonances](resonances/) - what placing two or more of these topics side by side generates, written by `/resonate`
```

One entry per `topics/*.md` other than `index.md`, alphabetical by slug,
built from `title`, `description`, the date of `generated.at`, N from
`sources`, and the bold headline under `### Most Pressing Thread`. Write
`not recorded` for anything missing (the slug, for a missing title). Include
Resonances only if `topics/resonances/` exists. List each unconformed
`topics/*/distillation.md` too, in the same order, as
`- [{slug}]({slug}/distillation.md) - (stale: pre-0.13.0)`.

### 5. Commit

**Commit** as in `operating-model.md`, with `verified` set on the
distillation:

```bash
commonplace --root "$PWD" git -- add topics/{slug}.md topics/index.md .commonplace/skills/synthesize/{slug}.md
commonplace --root "$PWD" git -- commit -m "Synthesize: {topic name}"
```

Then name to the user the resonances written against the old distillation
(`grep -l '^  - {slug}$' topics/resonances/*.md`).

### 6. Agent Journal (optional)

This step is yours: **Agent journal** in `operating-model.md`.

### 7. Land

**Land** as in `operating-model.md`. The user's approval in step 3 is the
go-ahead.
