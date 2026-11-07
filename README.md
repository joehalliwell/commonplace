# Commonplace

A personal knowledge management tool for archiving and organizing your notes,
journal entries and AI conversations into a searchable digital archive.

Commonplace is named after the [commonplace
book](https://en.wikipedia.org/wiki/Commonplace_book) that scholars used in
antiquity. [MANIFESTO.md](https://github.com/joehalliwell/commonplace/blob/main/MANIFESTO.md) says what it is for; the
[handbook](https://github.com/joehalliwell/commonplace/blob/main/docs/handbook.md) says how it behaves.

## What it does

- 🛰️ **Fetches conversations** straight from Claude, Gemini and ChatGPT, using
  your browser session, along with your local Claude Code sessions, and mirrors
  their memory and Google Keep
- 💬 **Imports** vendor exports
- 📁 **Stores everything as markdown** in a git repository, under readable
  paths: `chats/claude/2026/06/2026-06-28-conversation-title.md`
- 🔍 **Searches** by meaning and by keyword, with embeddings computed locally
- 🏷️ **Annotates** any note with tags and links, kept beside it, so fetches
  never overwrite them
- 🤖 **Claude Code skills** for synthesizing topics and raking up unmade plans

## Installation

```bash
pip install uv
uv tool install commonplace
```

## Setup

```bash
# 1. Create your commonplace (a git repo, with scaffolding)
commonplace init ~/commonplace

# 2. Tell every other command where it lives
export COMMONPLACE_ROOT=~/commonplace

# 3. Pull in your conversations
commonplace fetch
```

`init` is the one command that takes the path as an argument rather than
reading `COMMONPLACE_ROOT` — there's no repo to open yet. Everything past
step 3 is optional.

## Commands

Each command's options are in `commonplace <command> --help`.

| Command           | What it does                                            |
| ----------------- | ------------------------------------------------------- |
| `init`            | create a commonplace                                    |
| `fetch`           | pull new conversations, memory and Keep notes           |
| `import`          | import an export, a wire archive or a directory of them |
| `search`          | find notes by meaning and keyword                       |
| `index`           | index what isn't yet, or rebuild the index              |
| `journal`         | open today's (or a given day's) journal entry           |
| `stats`           | activity heatmap and per-source counts                  |
| `ls`              | a folder's notes with their titles and descriptions     |
| `tag`, `untag`    | tag notes, in their marginalia                          |
| `link`, `unlink`  | link one note to another, saying why                    |
| `show`, `resolve` | everything known about a note, or just its path         |
| `sync`            | commit and sync with your git remote                    |
| `git`             | run git against your commonplace from anywhere          |
| `doctor`          | restore scaffolding, re-attach marginalia, check links  |
| `config`          | print the settings in effect                            |

## Claude Code skills

To enable the skills, run in Claude Code:

```
/plugin marketplace add joehalliwell/commonplace
```

`/synthesize`, `/resonate`, `/rake`, `/project` and `/dream` then work in your
commonplace; the [handbook](https://github.com/joehalliwell/commonplace/blob/main/docs/handbook.md#claude-code-skills) says what each
does.
