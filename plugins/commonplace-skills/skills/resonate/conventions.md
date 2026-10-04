# Resonate: Conventions and Conforming

## Conventions

What each release changed about the artefact. An entry is named by the
plugin release that introduced it. Add one only for a change a reader would
notice: each entry makes every existing resonance stale.

- **0.13.0** — A resonance is an OKF v0.2 concept document with
  `type: Topic`, a `title` and one-sentence `description`, `generated` naming
  the release that wrote it, and `verified` naming who approved it.
  `source_distillations` point at the flat `topics/<slug>.md`, and `updated`
  is gone.
- **0.12.0** — Citations in the body are root-relative wikilinks,
  `[[/<source path without .md>]]`, with no date beside them. Frontmatter
  paths stay bare. Every cited path resolves.
- **0.10.0** — Crossings and tensions restate what each topic contributes and
  name the topics. The Most Live Question is a headline sentence. Revisions
  lines are one sentence.
- **0.9.0** — Only primitives are quoted. Attribution and citations are
  carried through from the distillations. *Stopped* threads are never read as
  resolved. The resonance has a Revisions section.

## Conforming a Stale Resonance

When only the conventions are stale, conform the resonance in its own commit
before any new reading, so `git show` on that commit is exactly what the
upgrade changed. Spawn the subagent as in step 3, appending:

> **Conform only.** Search for no new material. Bring the resonance into line
> with the rules in this prompt, paying particular attention to these
> changes: \<the Conventions entries newer than its `generated.by`, or all of
> them>. The Revisions line is
> `<date> — Conformed to resonate@<version>; no new material.`

Review as in step 4, and commit as `Conform: {topics} to resonate@{version}`.
