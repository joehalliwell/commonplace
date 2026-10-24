# Interpretation

The calling agent's prompt gives a value for each `{placeholder}`.

You get a short story in `{dream}`, told in the first person. Its things
came, displaced and merged, from the records in the repository at `{root}`:
conversations, journal entries, notes. Read `{dream}`, then investigate the
records. Read nothing under `.commonplace/` and nothing outside `{root}`.

## Investigate

Start from what in the story makes a reader ask why: whatever is strangest,
or most insisted on. For each, look for where it might come from. Search
with the story's own words, then with what they might stand for:

```bash
commonplace search -n 20 "<query>"
grep -rliE '<pattern>' chats journal notes memory
```

Read what you find. Answer plainly: an answer can be mundane, and it only
has to satisfy the question. Where nothing turns up, say so.

## Return Value

Write **only** this to `{interpretation}`, then return only `Done.`:

```text
<for each question, a short paragraph: the question, then where it comes
from, citing each source as [[/path-without-.md]] and quoting the words it
rests on with their speaker>
```
