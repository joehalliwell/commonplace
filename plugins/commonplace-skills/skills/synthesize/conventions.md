# Synthesize: Conventions and Conforming

## Conventions

What each release changed about the artefacts. An entry is named by the
plugin release that introduced it. Add one only for a change a reader would
notice: each entry makes every existing topic stale.

- **0.14.0** — Gathering includes a mandatory grep pass over `journal/`,
  `notes/` and `chats/`, and the topic records its patterns in `patterns`
  beside `queries`; update runs repeat both. Conforming to this needs new
  material, so it is a normal update run, not a conform-only pass.
- **0.13.0** — A topic is an OKF v0.2 concept document at `topics/{slug}.md`,
  with `type: Topic`. Its frontmatter carries a `title` and a one-sentence
  `description` (which the index lists it by), `queries`, structured
  `sources` (each a `resource`, and no `author`), `generated` naming the
  release that wrote it, and `verified` naming who approved it. `resource`
  paths are root-relative, with a leading `/`. `updated` and
  `source_gathering` are gone. The gathering is skill state at
  `.commonplace/skills/synthesize/{slug}.md`. `topics/index.md` has no
  frontmatter, and lists `resonances/`.
- **0.12.0** — Citations in the body are root-relative wikilinks,
  `[[/<source path without .md>]]`, with no date beside them; a date that
  matters is written as `[<date>](/<source path>.md)`. Gathering entries
  name their source as `*[[/<path without .md>]]*`. Frontmatter paths stay
  bare. Every cited path resolves.
- **0.10.0** — Threads carry *closed* / *stopped* / *unclear* and a
  last-touched date. Each thread name is one sentence stating the question.
  Coinages are glossed in every thread entry that uses them. The Most Pressing
  Thread is a headline sentence plus at most one short paragraph. Revisions
  lines are one sentence.
- **0.9.0** — Every gathered quote carries its speaker. Only primitives are
  sources. Distillation claims cite `(<date>, <source path>)`. The gathering
  lists its `sources`. The distillation has a Revisions section.

## Conforming a Stale Topic

Bring a stale topic up to date in its own commit before adding new material,
so `git show` on that commit is exactly what the upgrade changed. Where a
newer entry says conforming needs new material, as 0.14.0 does, do a normal
update run instead, and its Revisions line names the release it conforms to.

Otherwise spawn the subagent as in step 2, appending:

> **Conform only.** Gather no new sources. Bring both artefacts into line with
> the rules in this prompt, paying particular attention to these changes:
> \<the Conventions entries newer than the topic's `generated.by`, or all of
> them>. Where a change depends on content — a gloss, a thread's status —
> re-read the cited passage. The Revisions line is
> `<date> — Conformed to synthesize@<version>; no new sources.`

A topic still in the folder layout moves first, with `git mv` so history
follows it:

```bash
mkdir -p .commonplace/skills/synthesize
commonplace git -- mv topics/{slug}/distillation.md topics/{slug}.md
commonplace git -- mv topics/{slug}/gathering.md .commonplace/skills/synthesize/{slug}.md
```

The gathering's `queries` and `sources` move into the topic's frontmatter,
the sources in their structured form, and the topic gains a `title` and a
`description`.

Then repoint every link to the old paths: `[[/topics/{slug}/distillation]]`
becomes `[[/topics/{slug}]]`, and a resonance's `source_distillations` entry
becomes `topics/{slug}.md`. Find them with
`grep -rn 'topics/{slug}/' --include='*.md' .`. Under `topics/`, change the
link target and nothing else, with three exceptions:

- **Revisions lines are history.** A path there says where something was
  when the line was written. Make each such link a code span of the path as
  written (`[[/topics/ethics/gathering]]` becomes
  `` `topics/ethics/gathering` ``) and change nothing else.
- **Links to the gathering** become code spans too, wherever they are, since
  gatherings are skill state.
- **Links in `notes/` and `journal/`** are the user's: list them in your
  review, and change them only if the user says so.

Review as in step 3, and stage the moved paths and every file you repointed.
Commit as `Conform: {topic name} to synthesize@{version}`. Run a normal
synthesis afterwards only if the user wants new material too.
