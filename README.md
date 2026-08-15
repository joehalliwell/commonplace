# Commonplace

A personal knowledge management tool for archiving and organizing your notes,
journal entries and AI conversations into a searchable digital archive.

Commonplace is named after the [commonplace
book](https://en.wikipedia.org/wiki/Commonplace_book) that scholars used in
antiquity.

## Features

### Current Capabilities

- 🛰️ **Fetch conversations** straight from the provider, using your browser
  session: Claude, Gemini, ChatGPT
- 💬 **Import conversations** from manual exports and local logs:
  - Claude (ZIP export from claude.ai)
  - ChatGPT (ZIP export)
  - Gemini (Google Takeout HTML export)
  - Claude Code (`.jsonl` session logs from `~/.claude/projects/`)
- 📁 **Standardized storage** as organized markdown files with metadata
- 🗂️ **Date-based organization** in a clear directory structure:
  ```
  ~/commonplace/
  ├── chats/                    # AI conversations (fetched or imported)
  │   ├── claude/2026/06/2026-06-28-conversation-title.md
  │   ├── chatgpt/2026/06/2026-06-28-conversation-title.md
  │   ├── claude-code/2026/06/2026-06-28-session-title.md
  │   ├── gemini/                       # fetched from gemini.google.com
  │   └── gemini-takeout/               # imported from Google Takeout
  ├── journal/2026/06/2026-06-28.md     # daily entries
  ├── notes/                    # Manual notes and thoughts
  └── .commonplace/             # config, attachments, and the search index
  ```
- ✨ **Rich markdown format** with frontmatter, timestamps, and proper formatting
- 🔄 **Git integration** for change tracking and automatic commits when importing conversations
- 🔍 **Full-text and semantic search** using local vector embeddings to find
  relevant conversations by meaning
- 🤖 **Claude Code skills** for synthesizing topics and projects out of the archive

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

## Usage

### Fetch conversations

The main way in: pull new conversations straight from the provider, no export
request or download to wait for.

```bash
# Fetch from all sources
commonplace fetch

# Restrict to particular sources (repeatable)
commonplace fetch --source claude
commonplace fetch -s gemini -s chatgpt

# Ignore the cursor and pull everything the provider has
commonplace fetch --all

# Skip indexing this run (see `commonplace index`)
commonplace fetch --no-index
```

`fetch` reads your logged-in session cookies from Chrome — log in once in the
browser and the session lasts several weeks (Claude) or a few days (Gemini,
with auto-refresh). The incremental cursor is derived from git history (last
commit touching `chats/{source}/`), so subsequent runs only pull
conversations updated since the previous fetch.

The three sources — `claude`, `gemini`, `chatgpt` — land in
`chats/claude/`, `chats/gemini/` and `chats/chatgpt/`. Gemini's fetcher gets
per-turn timestamps, Gem personas and thought traces, which the Takeout export
doesn't have. Claude's gets slightly less than the manual export: the endpoint
strips `<antThinking>` blocks server-side (issue #6).

These are the providers' internal endpoints — unofficial, and they change
without notice. If a fetcher breaks, fall back to
[manual exports](#importing-exports-and-local-logs); if a provider starts
rejecting you as a bot, see [Configuration](#configuration).

**If you previously imported Gemini history from Takeout**, move it aside
before the first `fetch --source gemini` — the fetcher owns `chats/gemini/`,
and the Takeout importer now writes to `chats/gemini-takeout/`:

```bash
commonplace git mv chats/gemini chats/gemini-takeout
commonplace git commit -m "Migrate Takeout Gemini imports to gemini-takeout path"
```

### Search your conversations

Notes are indexed as they are committed, so the index is usually current.

```bash
# Hybrid search - semantic and keyword combined (default)
commonplace search "explain neural networks"

# Semantic search - finds content by meaning
commonplace search "explain neural networks" --method semantic

# Keyword search - full-text matching only
commonplace search "explain neural networks" --method keyword

# Limit number of results (default: 10)
commonplace search "machine learning" --limit 5

# Include notes deleted since they were indexed
commonplace search "machine learning" --include-deleted
```

Results only ever point at notes the repository still holds: one deleted since
the last index run is hidden rather than quoted back at you, and
`--include-deleted` reaches it while it is still in the index. A note you have
merely *edited* keeps matching on its old text until the next index run — it is
still there to open, so a slightly stale quote beats losing the note from
search in the meantime.

Embeddings are computed locally (fastembed, `BAAI/bge-small-en-v1.5`) — the
model downloads on first use and nothing leaves your machine. The index lives
at `.commonplace/cache/index.db` and is not tracked by git.

```bash
# Index anything not yet indexed (e.g. after --no-index, or notes added by hand)
commonplace index

# Rebuild from scratch
commonplace index --rebuild

# Keep chunks for deleted and edited notes instead of dropping them
commonplace index --no-prune
```

Each run also drops chunks for notes that have been deleted or edited since
they were indexed, so the index tracks the repository instead of accumulating
every version of everything.

### Journal

```bash
# Open today's entry in $EDITOR
commonplace journal

# Open a specific day
commonplace journal 2026-06-28
```

Entries live at `journal/{year}/{month}/{date}.md`. Saving and exiting the
editor commits the entry; leaving it unchanged does nothing.

### See what you have

```bash
# Activity heatmap and per-source counts for the last 52 weeks
commonplace stats

# Full history
commonplace stats --all

# One source (these are repo paths: chats/claude, chats/gemini, journal, notes)
commonplace stats --source chats/claude
```

### Sync your commonplace

If you have a git remote configured, sync your changes:

```bash
# Sync with default remote (origin), auto-commit changes
commonplace sync

# Sync with specific remote
commonplace sync --remote upstream

# Use merge instead of rebase
commonplace sync --strategy merge

# Don't auto-commit uncommitted changes
commonplace sync --no-auto-commit

# Sync a branch other than the current one
commonplace sync --branch main
```

For anything sync doesn't cover, `commonplace git` runs git against the repo
wherever you happen to be:

```bash
commonplace git log --oneline -10
commonplace git status
```

### Check your repo

```bash
commonplace doctor
```

Restores any scaffolding that has gone missing (`.gitignore`,
`.gitattributes`, `.claude/settings.json`, `.commonplace/config.toml`) and
diffs the managed files against the templates `init` currently writes. Run it
after upgrading commonplace to see what an older repo is missing. It only
reports — applying the diff is up to you.

## Importing exports and local logs

`fetch` covers the three chat providers. Import is for everything else: local
logs, historical archives, and conversations a fetcher can't reach (see the
`<antThinking>` caveat above).

```bash
# A provider export, or a wire archive written by `fetch`
commonplace import path/to/export.zip

# A directory: every file an importer recognizes, recursively
commonplace import ~/Downloads/exports/

# Your local Claude Code sessions
commonplace import ~/.claude/projects/
```

The format is detected per file — Claude export, ChatGPT export, Gemini
Takeout, Claude Code session log, or wire archive — and files no importer
claims are skipped. Re-importing a conversation updates it in place: fields
the importer owns are refreshed, and frontmatter you added by hand survives.

<details>
<summary>How to export from each provider</summary>

**Claude**: [claude.ai](https://claude.ai) → profile icon (bottom left) →
**Settings** → **Data & Privacy** → **Export data**. You'll get an email with
a download link, usually within a few minutes.

**ChatGPT**: [chatgpt.com](https://chatgpt.com) → profile icon →
**Settings** → **Data controls** → **Export data** → confirm. The email can
take up to 24 hours.

**Gemini**: [Google Takeout](https://takeout.google.com) → **Deselect all** →
select **My Activity** → **Multiple formats**, ensure HTML is selected →
**All activity data included**, select only **Assistant** → **Next step** →
**Create export**. Can take several hours.

⚠️ Export links are temporary and typically expire after 7 days.

</details>

## Claude Code skills

`init` writes a `.claude/settings.json` that registers this repo's plugin
marketplace, so Claude Code sees the skills when you open your commonplace.
To enable them, run in Claude Code:

```
/plugin marketplace add joehalliwell/commonplace
```

| Skill                       | What it does                                             |
| --------------------------- | -------------------------------------------------------- |
| `/synthesize [topic]`       | gather and distil a topic into `topics/{slug}/`          |
| `/resonate <slug> <slug> …` | surface interference patterns between synthesized topics |
| `/projects`                 | scan for candidate projects, update `projects/index.md`  |
| `/project <sketch>`         | extract a project artefact into `projects/{slug}/`       |

Artefacts have no dated filenames — git is the versioning layer, and repeat
runs update them in place.

## Configuration

The defaults are meant to work untouched. To change one, set an environment
variable named after it, upper-cased with a `COMMONPLACE_` prefix — e.g.
`COMMONPLACE_EDITOR="code --wait"`.

| Setting      | Default                     | Purpose                                    |
| ------------ | --------------------------- | ------------------------------------------ |
| `root`       | platform data dir           | where your commonplace lives               |
| `user`       | your login name, titlecased | how you're named in imported conversations |
| `editor`     | `$EDITOR`, else `vim`       | editor used by `commonplace journal`       |
| `wrap`       | `80`                        | target line length for written markdown    |
| `auto_index` | `true`                      | index new notes as they're committed       |
| `ua`         | a current Chrome UA         | User-Agent sent by fetchers                |

`ua` is the one worth knowing about: every provider fronts its internal API
with a bot check that a stale User-Agent fails, so if fetches start getting
blocked, copy `navigator.userAgent` from your browser's console and set
`COMMONPLACE_UA` to it — no need to wait for a release.

⚠️ `init` seeds a `.commonplace/config.toml`, but nothing reads it yet; the
environment is the only channel that currently works.
