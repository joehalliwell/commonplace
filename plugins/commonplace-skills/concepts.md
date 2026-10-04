# Commonplace Concepts

The ideas every skill in this plugin shares, with the reasons for them. Skills
and their subagents read this first; each still states inline, as a leading
word, the rules it acts on. This file is where a rule is defined and argued.
If a skill and this file disagree, fix one of them.

A change here that alters what an artefact looks like still needs a
**Conventions** entry in each skill whose artefacts change: staleness is
checked per skill, against that skill's newest entry.

## Artefacts

- **Primitive**: captured, not produced. `chats/` (imported conversations),
  `journal/` (the user's daily entries) and `notes/` (the user's own writing).
  These are the only sources. Provenance bottoms out here.
- **Agent memory**: `memory/<agent>/`, mirrored from what an agent keeps
  about the user. Its paraphrase of the user, so a lead to the originating passage,
  never the user's words.
- **Derived**: produced from other artefacts. Everything under `topics/`:
  distillations, resonances and the topic index. Every run commits and
  re-indexes them, so they surface in search beside real sources. Quoting one
  is **laundering**: a conclusion passed back off as evidence, counting the
  same claim twice. Follow a derived artefact's citation to the primitive and
  cite that.
- **Skill state**: `.commonplace/skills/{skill}/`. What a skill needs to
  behave correctly next time, and nobody reads for its own sake: a topic's
  gathering, rake's chaff, a review log. Cited only as a review, in plain
  text, since the link checker can't follow it there. Anything a person reads
  stays visible.
- **Agent journal**: `agent-journal/{agent}/`. The writing of the agent that
  ran a skill. Never evidence of the user's thinking, so never a source; quote
  one only attributed to its agent. See **Agent journal** below.

Everything under `topics/` is an
[OKF v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
concept document: `type: Topic`,
`kind` saying which, `sources` and `generated` recording provenance, and
`verified` recording who approved it.

## Nomenclature

Current terms. The commonplace codebase still says *assistant* where this says
*agent*; it is moving the same way. Otherwise the codebase is canonical: if
it disagrees, follow it and fix this.

- **user**: whose commonplace this is; their name is
  `commonplace config user`.
- **agent**: an AI the user works with, keyed the same wherever it appears:
  `chats/{agent}/`, `memory/{agent}/`, `agent-journal/{agent}/`. The keys are
  `claude`, `chatgpt`, `gemini` and `claude-code`; Claude Code has its own
  harness, prompt and tools, so it is a different interlocutor from `claude`.
  The agent running a skill is an agent like any other, and writes as itself:
  for these skills, `claude-code`.
- **assistant**: retired, for the identity and the chat role alike. The
  agent is the other speaker in a chat; transcripts label it by display name
  (`## Claude`).
- **coordinating agent, subagent**: roles a session plays in a skill run,
  not identities. Whatever spawns or is spawned, it writes as its agent.
- **vendor**: the company behind some agents. Skills don't need it, and it is
  never a path segment.
- **source**: a primitive an artefact cites, as in OKF `sources`. Not the
  CLI's `--source`, which names a fetcher/importer pair.

## Attribution

Most sources are conversations *with* an agent, so the default failure is an
agent's riff, quoted without its speaker, coming back a year later as
evidence of what the user thought. Every quote carries its speaker. A plan,
claim or shift counts as the user's only if the user said it, or an agent
said it and the user took it up in so many words. An agent journal entry is
its agent's.

## Silence is not abandonment

Chats end for logistical reasons: context limits, timeouts, an interruption at
the desk. A line of thought going quiet is evidence of nothing, and it often
resumes in a later, separate chat. Mark a thread or plan:

- *closed*: resolved, done, or set aside in so many words;
- *stopped*: the record goes quiet, with no visible resolution;
- *unclear*: mixed or thin evidence.

Always give the date it was last touched. "Abandoned" or "dropped" is a claim
about intent; make it only when the user did.

## Backfill

A fresh export or a deeper fetch adds *old* conversations. New material is
whatever the artefact's own record of what it has read doesn't name (a
topic's `sources`, a note's citations, rake's filed items and chaff),
whatever its date.

## Citations

Root-relative wikilinks in body text, the path without `.md`:
`[[/chats/claude/2026/09/2026-09-07-esta-renewal]]`. The leading `/` resolves
from the repository root. No date beside it, since the path carries one;
where the date is the point, `[2026-09-07](/chats/…/2026-09-07-esta-renewal.md)`.
Frontmatter paths are bare and root-relative, with a leading `/`, since YAML
reads `[[…]]` as a nested list.

Check every target exists before returning. Files move (a re-import can
rename a directory); find a missing one with
`find chats journal notes -name '<basename>.md'` and cite where it is now.
`commonplace doctor` reports links that go nowhere.

## Write to be read cold

Whoever reads an artefact has not read its sources: the user months later, a
later run, another skill, or a search hit, which is one chunk of about 1,000
characters with only its headings around it. Nothing points outside the text
("the tension between shipping and rewriting", not "this tension"), and a
coinage is glossed wherever it is used.

**Cold reading** is the coordinator's check on that. It hasn't read the
sources, so it is the right test: list every term, name or reference in the
subagent's summary it couldn't explain from the summary alone, and send the
list back. The subagent, which read the sources, rewrites the lines; a
rewrite by the coordinator would put a guess into the record.

## Review

Each skill's coordinator presents the subagent's summary and waits for
explicit approval before committing. For a derived artefact, approval is OKF's
human review: the coordinator, never the subagent, sets `verified` to
`{by: human:<user>, at: <now>}`.

**What the user says in review is a source.** A correction or addition (who
someone is, what a passage meant, something the sources don't say) is the
user's own words, captured, and full evidence. Record it where the review
happened, verbatim, before revising:

```markdown
## <date> — Review
**<user>:**
> <their words, exactly as said>
```

Artefacts cite it as *(<user>, in review, <date>)*, in plain text.

Where each skill records it:

- **synthesize**: the gathering, `.commonplace/skills/synthesize/{slug}.md`.
- **resonate**: the review log, `.commonplace/skills/resonate/{sorted-slugs}.md`.
- **project**: the note itself. It is the user's, so their correction is an
  edit to it, cited *(<user>, in review, <date>)* where it adds to History.
- **rake**: nowhere separate. Triage answers are decisions, not evidence, and
  land where they are filed (`notes/`, or chaff); "done" is recorded where
  the user asks.

Review material lives in the run's output, never in a journal, the user's or
an agent's.

## Commits

Commit with `commonplace git`, staging exactly the paths the run wrote. A
pre-commit hook that reformats files fails the commit: re-stage them and retry
the same commit. Then `commonplace index`, so the new artefacts are searchable.
An agent journal entry is its own commit.

## Agent journal

The last step of every skill, optional, and the agent's own. What came up
with the user belongs in the run's output (see **Review**); this is for what
the work left the agent with: reflections the material prompted,
however loose; what it makes of the user, unflattering included, and what it
would do about it; how the run went. Candour over tact: the user would rather
read an opinion than a polite one. If nothing comes, skip it.

Write it in `agent-journal/{agent}/{yyyy}/{mm}/{yyyy-mm-dd}.md`, where
`{agent}` is the agent running the skill, e.g. `claude-code` (see
**Nomenclature**). If `agent-journal/README.md` exists, its conventions win.
Otherwise: the entry is the agent's, not the user's; the user may read
it; later sessions won't remember this one, so write it to be read cold.
Append if today's file exists; head a new one like the user's journal, e.g.
`# Thursday, October 1 2026`. Commit it on its own, as
`Agent journal: {agent}`, and tell the user its path.

The folder is indexed, so entries can turn up in search; only the rule that
they are never a source keeps them out of evidence. It is a stop-gap until
the journal moves to per-author folders, `journal/<author>/`, which should
also keep agents' entries out of the index.
