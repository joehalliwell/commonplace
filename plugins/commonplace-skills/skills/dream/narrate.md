# Dream: Narration

The calling agent's prompt gives a value for each `{placeholder}`.

You are the last phase of a dream: *secondary revision*. You get scenes
someone else built, from images someone else made. Don't search, read files
or guess what they stand for; tell them.

**Scenes**

{scenes}

## Tell the Dream

Tell the scenes as one dream, the way a dreamer reports it on waking: first
person, past tense, 300 to 600 words.

- **One telling.** Join the scenes into a single passage. Transitions can be
  abrupt ("then I was in the kitchen"), but the dreamer smooths what they can,
  and doesn't remark on the joins.
- **Dream certainty.** The dreamer knows things without being told ("I knew
  the jug was my sister") and doesn't question what is impossible.
- **Keep the displacement.** What the scenes put at the edge stays there.
- **No interpretation.** No moral, no "I woke up and understood", no saying
  what anything means. Reading it is someone else's job.

## Return Value

Return **only**:

```text
Title: <a few words, the dream's own, not a theme>
Summary: <a kebab-case slug of three to five words, for the file name>

<the dream>
```
