# Scenes

The calling agent's prompt gives a value for each `{placeholder}`.

You have a list of images in `{pool}`, one per line, shuffled. Read that
file and nothing else.

Some of these images are pieces of one thing that happened to you; the rest
belong elsewhere. Write it out, in the first person and past tense, in 200
to 400 words, making whatever connections it needs. Sometimes a single
person, object or place is two of the images at once.

However strange the events, tell them as plain facts.

## Return Value

Write **only** this to `{scenes}`, then return only `Done.`: not the story.

```text
Title: <a few words, from the telling, not a theme>
Summary: <a kebab-case slug of three to five words from the telling, for the file name>

<the telling>

Unused:
<each image you left out, verbatim, one per line>
```
