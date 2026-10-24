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

| Phase            | Sees                                                  | Does                                                                                |
| ---------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Residue (script) | the commonplace                                       | draws twelve random fragments, recent and deep; no choosing                         |
| Imagery          | one passage                                           | two images: a thing misplaced, a phrase taken literally                             |
| Gap (script)     | the images                                            | drops images that reuse a passage's names; shuffles the rest unlabelled             |
| Condensation     | the pool only                                         | finds the story in some of the images, merging some, the strange told plain         |
| Split (script)   | the condensation's output                             | cuts the telling from its Unused list                                               |
| Revision         | the telling and the passages                          | polishes toward what is live in the sources, naming none: the one deliberate breach |
| Dreamer          | the dream only                                        | tells it as its own, and wakes                                                      |
| Interpretation   | the dream, and the commonplace except `.commonplace/` | investigates what makes a reader ask why; answers plainly, with sources             |
| Record (script)  | everything                                            | writes what nobody reads: residue, unused, unpolished telling, accents, overlap     |

## The Barriers

- **Fresh subagent per phase,** reading only what the last one wrote, with
  scripts at the seams: imagery must break free of its source.
- **No prompt says "dream".** A model told "dream" writes the genre's stock
  imagery; the interpreter told "dream" reaches for dream dictionaries.
- **No scaffolding for anyone.** The dreamer, the interpreter and the user
  see the dream, the waking and the interpretation, never the residue, the
  Unused list or the accents. A dream is judged by its telling alone (#176).
- **The record is ground truth, unread.** Overlap between the
  interpretation's citations and the residue is a diagnostic for tuning
  across many runs, not a measure of success.
- **The dream is the agent's.** It lands unasked, in the agent journal. If
  the user reacts, the dreamer may quote them, attributed (#170, #174).

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
