---
name: dream
description: Dream over random fragments of the commonplace, then record what the dream stirs
---

# Dream

You are running a dream over a commonplace repository: random fragments of
the record, pushed to images, fused and displaced, then told as one dream.
The steps follow Freud's dream-work: *day residue* (the fragments),
*representability* (images), *condensation* and *displacement* (fusing them
into a plot), *secondary revision* (your polish).

The dream is not evidence of anything. What it is for is **Waking**: the
user's reaction, in their own words, which is a source.

**Walls between phases.** The imagery must break free of the source material,
so each phase runs in a fresh subagent that sees only what the previous phase
returned, and you put a mechanical gap between imagery and condensation. You
hold the mapping back to the sources; no subagent gets a repository path, and
only you write to the worktree. Only you know it's a dream: the phase prompts
never say so, because a model told "dream" writes the genre's stock imagery,
and fresh subagents share that prior however high the walls. The one breach
is deliberate and last: your polish, which knows the sources.

## Prerequisites

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` and
`${CLAUDE_PLUGIN_ROOT}/operating-model.md` first: the concepts every skill
shares, and how every run goes from preflight to landing. The steps below
restate the rules they act on, and name the operating model's steps where
they run them. This skill departs from **Spawn**: it has two phase prompts
instead of one `subagent.md`, and passes them text, not a working directory.

## Workflow

### 0. Preflight and Enter

**Preflight** and **Enter** as in `operating-model.md`: settle uncommitted
files with the user, refresh the index, then work in a worktree
fast-forwarded to their branch.

### 1. Residue

Sample twelve fragments with the shell, never by choosing: a model's
"random" pick is a preference. Six are **recent**, from primitives touched in
the last week; six are **deep**, from anywhere. Top up from deep if recent
has fewer than six. Twelve is more than a dream holds: condensation keeps
what its plot turns on.

```bash
git log --since=7.days --name-only --format= -- chats journal notes | sort -u | shuf -n 6
git ls-files chats journal notes | shuf -n 6
```

Skip a path that no longer exists or was already picked, and draw again. In
each file, pick one `## ` section at random and take it up to the next `## `
heading, cut at 2,000 characters; a file with no `## ` heading is one
section:

```bash
grep -n '^## ' {file} | shuf -n 1
```

Note each fragment's path, its heading (for a chat, the speaker) and its
text. Any speaker counts, and any primitive, the journal's most private
entries included: it is the user's commonplace, and **Discard** in Waking is
the guard.

### 2. Imagery

Each phase's prompt is the text of its file beside this one, which you read
and send with its one placeholder filled: send the text, never the path,
which names the skill.

`imagery.md` goes to one subagent per fragment, all spawned in parallel,
each with `description` `"Imagery"` and `{fragment}` set to the fragment's
text and nothing else: no path, no heading, no date. Each returns two
images, one per line: something from the fragment as itself, misplaced, and
a phrase from it taken literally. Residue showing up
literally is how dreams work, so keep the fragment's things and words; an
image of what a fragment means or feels like makes the dream an allegory.

### 3. The Gap

Mechanical, in your own context. Drop any image that names a person,
product or place from its fragment: the things may come through, the names
may not. Then write what is left, unlabelled, one per line, to a scratch
file outside the worktree, and shuffle it:

```bash
shuf {pool file}
```

Record which images were dropped as leaked.

### 4. Condensation

`condense.md` goes to a fresh subagent, `description` `"Scenes"`, with
`{images}` set to the shuffled pool, one per line. It plots the images,
using at least a third, around someone who wants something, and returns a
title, a summary slug, the telling, and the images it left out. Check that
list against the telling yourself: it is the record of what went unused.

### 5. Secondary Revision

Yours, and the only phase that knows the sources. Polish the telling:
tighten it, and you may accentuate what resonates with the residue, an image
or detail that echoes something live in the fragments, so the dream leans
toward what is pertinent. The plot stays the subagent's. Don't name a source,
bring its words back, or say what anything means: a dream that explains its
residue is an allegory again. Keep the unpolished telling for the file.

Where the dream contradicts the user's waking life, you may mark it as a
dreamer telling it would: "My car. I don't have a car, I can't even drive.
But in this dream I did." Only for a fact the record states (`memory/`, the
residue, a quick search), never a guess, and once or twice at most: the
frisson is in the rarity.

### 6. Waking

Waking is this skill's **Review**, as in `operating-model.md`, without its
cold-reading revision: a dream is meant to fail a cold reading. Nothing is
revised; the user reacts.

Present the dream alone, with its title: no residue yet, so the sources
don't anchor the reading. Ask what it stirs with `AskUserQuestion`, options
**Something** (say what in the notes), **Nothing**, and **Discard**.

Then reveal the residue: each fragment's path and heading, the images it
became, which leaked or went unused, and what your polish accentuated. Ask
again, options **Keep** and **Discard**, with the notes for anything the
reveal changes.

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
<the dream, as polished>

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
- [[/<path without .md>]], <heading>: <its images, each marked used, unused or leaked>

## Unpolished
<the telling, as returned>
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
