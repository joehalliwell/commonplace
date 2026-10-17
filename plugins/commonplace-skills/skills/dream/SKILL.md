---
name: dream
description: Dream over random fragments of the commonplace, then record what the dream stirs
---

# Dream

You are running a dream over a commonplace repository: random fragments of
the record, pushed to images, fused and displaced, then told as one dream.
The steps follow Freud's dream-work: *day residue* (the fragments),
*representability* (images), *condensation* and *displacement* (fusing them,
moving emphasis), *secondary revision* (the story).

The dream is not evidence of anything. What it is for is **Waking**: the
user's reaction, in their own words, which is a source.

**Walls between phases.** The imagery must break free of the source material,
so each phase runs in a fresh subagent that sees only what the previous phase
returned, and you put a mechanical gap between imagery and condensation. You
hold the mapping back to the sources; no subagent gets a repository path, and
only you write to the worktree.

## Prerequisites

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` and
`${CLAUDE_PLUGIN_ROOT}/operating-model.md` first: the concepts every skill
shares, and how every run goes from preflight to landing. The steps below
restate the rules they act on, and name the operating model's steps where
they run them. This skill departs from **Spawn**: it has three phase prompts
instead of one `subagent.md`, and passes them text, not a working directory.

## Workflow

### 0. Preflight and Enter

**Preflight** and **Enter** as in `operating-model.md`: settle uncommitted
files with the user, refresh the index, then work in a worktree
fast-forwarded to their branch.

### 1. Residue

Sample six fragments with the shell, never by choosing: a model's "random"
pick is a preference. Three are **recent**, from primitives touched in the
last week; three are **deep**, from anywhere. Top up from deep if recent has
fewer than three.

```bash
git log --since=7.days --name-only --format= -- chats journal notes | sort -u | shuf -n 3
git ls-files chats journal notes | shuf -n 3
```

Skip a path that no longer exists or was already picked, and draw again. In
each file, pick one `## ` section at random and take it up to the next `## `
heading, cut at 2,000 characters; a file with no `## ` heading is one
section:

```bash
grep -n '^## ' {file} | shuf -n 1
```

Note each fragment's path, its heading (for a chat, the speaker) and its
text. Any speaker counts.

### 2. Imagery

One subagent per fragment, all spawned in parallel, each with `description`
`"Dream: imagery"` and this prompt:

```text
Follow ${CLAUDE_PLUGIN_ROOT}/skills/dream/imagery.md (resolve the path), with this fragment:

<the fragment's text, and nothing else: no path, no heading, no date>
```

Each returns two or three images, one per line.

### 3. The Gap

Mechanical, in your own context. For each fragment's images, drop any that
reuses a capitalised word from its fragment (a name leaking through), except
at the start of a sentence. Then write what is left, unlabelled, one per
line, to a scratch file outside the worktree, and keep a random two thirds,
`{n}`, rounded down:

```bash
shuf -n {n} {pool file}
```

Record which images were dropped, and why: leaked or forgotten.

### 4. Condensation

A fresh subagent, `description` `"Dream: condensation"`:

```text
Follow ${CLAUDE_PLUGIN_ROOT}/skills/dream/condense.md (resolve the path), with these images:

<the shuffled pool, one per line>
```

It returns three to five scenes.

### 5. Narration

A fresh subagent, `description` `"Dream: narration"`:

```text
Follow ${CLAUDE_PLUGIN_ROOT}/skills/dream/narrate.md (resolve the path), with these scenes:

<the scenes, as returned>
```

It returns a title, a short summary slug and the dream.

### 6. Waking

Waking is this skill's **Review**, as in `operating-model.md`, without its
cold-reading revision: a dream is meant to fail a cold reading. Nothing is
revised; the user reacts.

Present the dream alone, with its title: no residue yet, so the sources
don't anchor the reading. Ask what it stirs with `AskUserQuestion`, options
**Something** (say what in the notes), **Nothing**, and **Discard**.

Then reveal the residue: each fragment's path and heading, the images it
became, and which were dropped. Ask again, options **Keep** and **Discard**,
with the notes for anything the reveal changes.

On **Discard**, at either question, `ExitWorktree` with `action: remove`:
nothing is written or landed. On **Keep**, write the dream file
(`.commonplace/skills/dream/{agent}/{yyyy}/{mm}/{yyyy-mm-dd}-{summary}.md`,
where `{agent}` is you, e.g. `claude-code`):

```markdown
---
title: <title>
residue:
  - /<path of each fragment>
generated: {by: dream/<plugin release>, at: <now, e.g. 2026-10-01T14:00:00Z>}
---

# <title>

## Dream
<the dream, as returned>

## Waking
**<agent>:**
> What does it stir?

**<user>:**
> <their words, exactly as said, or "Nothing.">

**<agent>:**
> <the residue, revealed: does that change anything?>

**<user>:**
> <their words, exactly as said>

## Residue
- [[/<path without .md>]], <heading>: <its images, kept and dropped, each marked>

## Scenes
<the scenes, as returned>
```

**What the user says on waking is a source**, recorded verbatim, so record
it before anything else and never paraphrase it. Every residue target exists
as `<path>.md`.

### 7. Commit

**Commit** as in `operating-model.md`:

```bash
commonplace --root "$PWD" git -- add .commonplace/skills/dream/
commonplace --root "$PWD" git -- commit -m "Dream: {title}"
```

### 8. Agent Journal (optional)

This step is yours: **Agent journal** in `operating-model.md`.

### 9. Land

**Land** as in `operating-model.md`. **Keep** is the go-ahead.
