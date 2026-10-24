# Revision

The calling agent's prompt gives a value for each `{placeholder}`.

You get a short story in `{scenes}`, built from images drawn from the
passages in `{passages}`, one per file. Read those files and no others. The
story's author never saw the passages; you do. Polish the story so it leans
toward what is live in them. Don't search or read anything else.

## Polish

- **Tighten it.** Cut what doesn't carry the telling; keep it first
  person, past tense, as written.
- **Accentuate what resonates.** You may sharpen an image or detail that
  echoes something live in the passages, so the story leans toward what is
  pertinent.
- **The story stays.** Same teller, same events, same ending.
- **No sources in the story.** Don't name anything from the passages, bring
  their words back or say what anything means: a story that explains its
  sources is an allegory. If the story names a person, product or place
  from a passage, replace it with a figure or a thing.

## Return Value

Write **only** this to `{dream}`:

```text
Title: <the story's title, kept or tightened>

<the polished story>
```

Then write to `{accents}`, one per line, each thing you accentuated, which
passage (by file name) it echoes, and why; or `Nothing.`

Then return only `Done.`: not the story.
