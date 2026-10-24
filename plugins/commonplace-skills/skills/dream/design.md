# Dream: Design

Why `/dream` is built the way it is. `SKILL.md` is the procedure. This file
is for whoever changes it, and no phase reads it.

## The Model

Dreaming loosens concerns so they rub against one another in a narrative.
Interpretation brings them back to the conscious mind, and the act of
interpreting is itself meaning-creating. Both are part of dreaming.

- **The dream should intrigue.** The right curiosity is mystery ("why does
  the drawing show my shower?"), not suspense ("will they get the
  passport?"): suspense is the plot's to answer, mystery the
  interpretation's.
- **The interpretation should satisfy that curiosity.** A mundane answer is
  a good one if it satisfies. Interpretation makes meaning, so it needn't
  recover the residue to succeed.

## Phases and What Each Sees

| Phase            | Sees                                                  | Does                                                                            |
| ---------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------- |
| Residue (script) | the commonplace                                       | draws twelve random fragments, recent and deep; no choosing                     |
| Imagery          | one passage                                           | two images: a thing misplaced, a phrase taken literally                         |
| Gap (script)     | the images                                            | drops images that reuse a passage's names; shuffles the rest unlabelled         |
| Condensation     | the pool only                                         | finds the story in some of the images, merging some, the strange told plain     |
| Teller (agent)   | the dream only                                        | presents it                                                                     |
| Reflection       | the dream, and the commonplace except `.commonplace/` | writes the journal entry: retells what it needs, asks why, answers with sources |
| Trace (script)   | everything                                            | keeps the telling as skill state; beside it, the residue and the overlap        |

## The Barriers

- **Fresh subagent per phase,** reading only what the last one wrote, with
  scripts at the seams: imagery must break free of its source.
- **No prompt says "dream".** A model told "dream" writes the genre's stock
  imagery; the interpreter told "dream" reaches for dream dictionaries.
- **No scaffolding for anyone.** The teller, the interpreter and the user
  see the dream and the reflection, never the residue or the images. A dream is judged by its telling alone (#176).
- **Nothing between the sources and the interpreter.** No phase after the
  gap sees the sources, so the interpreter finds connections nobody
  planted. A source-aware polish once did, and only made the interpretation
  easier and the overlap higher (#178).
- **The trace is for debugging, unread.** Overlap between the reflection's
  citations and the residue is a diagnostic for tuning across many runs, not
  a measure of success.
- **Whose dream is muddy.** It is the commonplace's material, dreamt
  through the process and told by the agent: not the user's, and not quite
  the agent's. The telling is skill state; the agent journal holds only the
  agent's own reflection on it, self-contained, so the journal stays the
  agent's thinking (#179). It lands unasked. If the user reacts, the agent
  may quote them, attributed (#170, #174).

## Every Line Is a Bias

Each rule in a phase prompt comes back in every dream, and a negative primes
what it forbids. Measured on fixed residue pools, classified blind (#169):

- A want that keeps going wrong made every dream a bureaucratic runaround
  (9/9 with a gatekeeper); without it, 0/9.
- Every line about people summoned the people it named: listed relations,
  then names, then "anyone related to you" (a father as himself in 6/9).
- Asking that a name bring in an image produced rebuses and famous
  engineers; a causal steer turned dreams into errands; "it is worth
  telling" did nothing.

So condensation's prompt is a bare brief. People and names come from the
residue or not at all. Change it only with a blind comparison on fixed
pools (`residue.py --seed`, `gap.py pool --seed`), and judge the telling,
never what it left out.
