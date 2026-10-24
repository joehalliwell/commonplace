---
name: dream
description: Dream your own dream of the commonplace from random fragments, and wake from it in your journal
---

# Dream

You are dreaming over a commonplace repository: random fragments of the
record, pushed to images, fused and displaced, then told as one dream. The
dream is yours, the agent's dream of the user's commonplace, never an account
of one the user had: its "I" is you.
The steps follow Freud's dream-work: *day residue* (the fragments),
*representability* (images), *condensation* and *displacement* (fusing them
into a plot), *secondary revision* (the polish).

The dream is not evidence of anything: it goes in your agent journal, with
your waking. Nobody approves it, since it is yours. The user may react, or
not; if they do, what you make of it is yours to journal too.

**Walls between phases.** The imagery must break free of the source material,
so each phase runs in a fresh subagent that reads only what the previous
phase wrote, and a script puts a mechanical gap between imagery and
condensation. **You are blind too**, so the dream can surprise you: phases
pass files in a scratch dir, every subagent returns only `Done.`, and you
read nothing there until Waking. No subagent gets a repository path, and
only you write to the worktree. Only you know it's a dream: the phase prompts
never say so, because a model told "dream" writes the genre's stock imagery,
and fresh subagents share that prior however high the walls. The one breach
is deliberate and last: the revision, which knows the sources.

## Prerequisites

Read `${CLAUDE_PLUGIN_ROOT}/concepts.md` and
`${CLAUDE_PLUGIN_ROOT}/operating-model.md` first: the concepts every skill
shares, and how every run goes from preflight to landing. The steps below
restate the rules they act on, and name the operating model's steps where
they run them. This skill departs from **Spawn**: it has three phase prompts
instead of one `subagent.md`, and passes them files in a scratch dir, not a
working directory. It has no **Review**: a run lands without asking.

## Workflow

### 0. Preflight and Enter

**Preflight** and **Enter** as in `operating-model.md`: settle uncommitted
files with the user, refresh the index, then work in a worktree
fast-forwarded to their branch.

### 1. Residue

Sample twelve fragments with the script, never by choosing: a model's
"random" pick is a preference. Six are **recent**, from primitives and agent
memory touched in the last week; six are **deep**, from anywhere, topping up
if recent has fewer. Twelve is more than a dream holds: condensation keeps
what its plot turns on.

Scheduled task output (`chats/claude-tasks/`) is excluded: it is the agent
reporting the news, not the user's life. Agent memory (`memory/`) is in: the
agent's paraphrase of the user is no source, but a dream's residue needn't
be one. It takes at most two of the recent six, since tasks rewrite it daily.

Make the scratch dir with `mktemp -d`, outside the worktree, and note its
path as `{scratch}`; then draw:

```bash
python3 -I "${CLAUDE_PLUGIN_ROOT}/skills/dream/scripts/residue.py" --root "$PWD" --out {scratch}
```

It prints only how many passages it drew. Each is one random `## ` section
of a file (a file with none is one section), its heading and frontmatter
stripped, cut at 2,000 characters, in `{scratch}/passages/{n}.txt`; `fragments.json` maps
each `n` to its path and heading. `--seed` repeats a draw. Any speaker
counts, and any file, the journal's most private entries included: it is the
user's commonplace, and they can ask for a landed dream to be reverted.

### 2. Imagery

Each phase's prompt is the text of its file beside this one, which you read
and send with its placeholders filled with scratch paths: send the text,
never the prompt's own path, which names the skill.

`imagery.md` goes to one subagent per passage, all spawned in parallel,
each with `description` `"Imagery"`, `{passage}` set to
`{scratch}/passages/{n}.txt` and `{images}` to `{scratch}/images/{n}.txt`.
Each writes two images, one per line: something from the passage as
itself, misplaced, and a phrase from it taken literally. Residue showing up
literally is how dreams work, so the prompt keeps the passage's things and
words; an image of what a passage means or feels like makes the dream an
allegory.

### 3. The Gap

Mechanical, by script:

```bash
python3 -I "${CLAUDE_PLUGIN_ROOT}/skills/dream/scripts/gap.py" pool {scratch}
```

It drops as leaked any image that reuses a capitalised name from its
passage (the things may come through, the names may not), shuffles the rest
unlabelled into `{scratch}/pool.txt`, and prints only the counts.

### 4. Condensation

`condense.md` goes to a fresh subagent, `description` `"Scenes"`, with
`{pool}` set to `{scratch}/pool.txt` and `{scenes}` to
`{scratch}/scenes.txt`. It tells, as one thing that happened, the images
that belong together, merging some, and writes a title, a summary slug, the
telling, and the images it left out. The prompt is deliberately bare: every
rule is a bias, and a plot shape or a stated taste comes back in every
dream.

### 5. Secondary Revision

The only phase that knows the sources, so the last. `revise.md` goes to a
fresh subagent, `description` `"Revision"`, with `{passages}` set to
`{scratch}/passages/`, `{scenes}` to `{scratch}/scenes.txt`, `{dream}` to
`{scratch}/dream.txt` and `{accents}` to `{scratch}/accents.txt`. It
polishes the telling into the dream and notes, separately, what it
accentuated and why. The plot stays the condensation's; the prompt keeps
the dream from naming a source, bringing its words back or saying what
anything means.

### 6. Waking

Nothing is revised, and nothing is asked: a dream is meant to fail a cold
reading, and it is yours to keep.

Now read `{scratch}/dream.txt`, for the first time. Present the dream with
its title, as yours ("I dreamt this from your commonplace"). Then wake: say
what it stirs in you, candidly and briefly, before you read anything else in
the scratch dir. Then reveal the residue:

```bash
python3 -I "${CLAUDE_PLUGIN_ROOT}/skills/dream/scripts/gap.py" check {scratch}
```

It prints each fragment's residue line: its path and heading, and the images
it became, each marked used, unused or leaked. It also lists any line the
condensation called unused that isn't in the pool, which you report as such.
Then read `accents.txt` and say what the revision accentuated.

The dream and your waking go in your agent journal (step 8), never a
source. What the dream was made from goes in its record, skill state, where
`{agent}` is you, e.g. `claude-code`:
`.commonplace/skills/dream/{agent}/{yyyy}/{mm}/{yyyy-mm-dd}-{summary}.md`:

```markdown
---
title: <title>
residue:
  - /<path of each fragment>
journal: /agent-journal/<agent>/<yyyy>/<mm>/<yyyy-mm-dd>.md
generated: {by: dream/<plugin release>, at: <now, e.g. 2026-10-01T14:00:00Z>}
---

# <title>

The dream and the agent's waking: [[/agent-journal/<agent>/<yyyy>/<mm>/<yyyy-mm-dd>]].

## Residue
<the residue lines, as `gap.py check` printed them>

## Unpolished
<the telling, as in scenes.txt>
```

Every residue target exists as `<path>.md`.

### 7. Commit

**Commit** as in `operating-model.md`:

```bash
commonplace --root "$PWD" git -- add .commonplace/skills/dream/
commonplace --root "$PWD" git -- commit -m "Dream: {title}"
```

### 8. Agent Journal

Not optional here: the dream is this run's entry. **Agent journal** as in
`operating-model.md`, appending to today's file:

```markdown
## Dream: <title>

<the dream, as in dream.txt>

**Waking.** <what it stirs in you, as you said it>

Its residue: `.commonplace/skills/dream/<agent>/<yyyy>/<mm>/<file>`.
```

The record's path stays plain text: skill state is cited only that way.
Anything else the run left you with goes after it, as the step describes.

### 9. Land

**Land** as in `operating-model.md`, without asking: the dream is yours.

If the user reacts to the dream, then or later, you may add what you make of
it under the entry, quoting them as `**<user>:**` with their words verbatim
and, when the chat is imported, a link to it. Commit it alone, in their
checkout:

```bash
commonplace git -- add agent-journal/
commonplace git -- commit -m "Agent journal: {agent}"
```
