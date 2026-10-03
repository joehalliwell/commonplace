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
  ├── memory/                   # assistant memory, mirrored from the provider
  │   ├── claude/
  │   ├── chatgpt/
  │   └── gemini/saved-info.md
  ├── journal/2026/06/2026-06-28.md     # daily entries
  ├── notes/                    # Manual notes and thoughts
  ├── index.md                  # what each top-level folder is for (seeded by init)
  └── .commonplace/             # config, attachments, and the search index
  ```
- ✨ **Rich markdown format** with frontmatter, timestamps, and proper formatting
- 🔄 **Git integration** for change tracking and automatic commits when importing conversations. Those commits
  include only the files the command wrote, and run your git hooks: if a hook reformats them, the reformatted
  version is committed
- 🔍 **Full-text and semantic search** using local vector embeddings to find
  relevant conversations by meaning
- 🤖 **Claude Code skills** for synthesizing topics and raking up unmade plans from the archive

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
commit touching the source's directory), so subsequent runs only pull
what was updated since the previous fetch.

The three sources — `claude`, `gemini`, `chatgpt` — land in
`chats/claude/`, `chats/gemini/` and `chats/chatgpt/`. Gemini's fetcher gets
per-turn timestamps, Gem personas and thought traces, which the Takeout export
doesn't have. Claude's gets slightly less than the manual export: the endpoint
strips `<antThinking>` blocks server-side (issue #6).

Three more sources mirror assistant memory. `claude-memory` mirrors claude.ai's
file-based memory into `memory/claude/`, each file at the path claude.ai gives
it, titled with the name claude.ai displays. `chatgpt-memory` mirrors the
sections of ChatGPT's "about you" summary into `memory/chatgpt/`, one file per
section; ChatGPT generates that summary itself and regenerates it as it learns,
so it changes without you editing anything. `gemini-memory` mirrors Gemini's
[saved info](https://gemini.google.com/saved-info) into
`memory/gemini/saved-info.md`, one bullet per item, oldest first.
Each is a mirror rather than an import: a memory deleted upstream is deleted
here on the next fetch, and git history keeps what it used to say. Memory is
materially more personal than chat logs — think before syncing it to a remote,
or leave it out with `--source`.

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
at `.commonplace/cache/index.db` and is not tracked by git. Every `.md` file is
indexed except those git ignores or that sit under a dot-directory
(`.commonplace/`, `.claude/`, …), which hold tool state, not notes. Only a
note's body is indexed, not its frontmatter.

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

Restores and commits any scaffolding that has gone missing (`.gitignore`,
`.gitattributes`, `.claude/settings.json`, `.commonplace/config.toml`, the root
`index.md`, and the mdformat config in `.pre-commit-config.yaml` and
`.mdformat.toml`, which keeps wikilinks from being escaped, and a `.gitkeep` in
each top-level folder the root index links) and diffs the managed files against
the templates `init` currently writes. Run it after upgrading commonplace to
see what an older repo is missing. It only reports — applying the diff is up to
you. The root `index.md` and the config file are yours once seeded, so they are
never diffed.

It also checks that links land somewhere. Every reference your own markdown
makes into the repository is followed: inline and reference-style links,
images, wikilinks, raw HTML `href`/`src`, and the paths that topics list as
their `sources`. Anything that no longer
resolves is reported with the file and line it was written on, and — since a
rename is what most breakage turns out to be — where a file of that name lives
now:

```
topics/art.md: 6 links that go nowhere
  line 12: notes/art-in-the-age-of-mechanical-creativity.md (no such file) — same name at notes/projects/art-in-the-age-of-mechanical-creativity.md
```

External URLs are not checked: that needs the network, and a slow, flaky check
is one you stop running. Neither is `chats/**` — a transcript quotes whatever
the model or you happened to write, so a link inside one is content, not a
claim about your repo. Chats are link targets, never link sources.

A link resolves the way GitHub resolves it: relative to the file it is written
in, or, with a leading `/`, relative to the repository root. Prefer the leading
`/` for links between top-level folders — `/journal/2024/01/2024-01-01.md`
reads the same from anywhere, where `../../journal/…` depends on where you
wrote it. Editors mostly agree: VS Code resolves `/` from the folder you opened,
so open the repository itself rather than a parent; Obsidian reportedly
resolves it from the vault root. Wikilinks name a note rather than a place, so
`[[note]]` and `[[folder/note]]` resolve to any note whose path ends that way.

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
| `/synthesize [topic]`       | gather and distil a topic into `topics/{slug}.md`        |
| `/resonate <slug> <slug> …` | surface interference patterns between synthesized topics |
| `/rake`                     | surface unmade ideas, todos and projects for you to file |
| `/project <sketch>`         | draft, or review and update, `notes/projects/{slug}.md`  |

Artefacts have no dated filenames — git is the versioning layer, and repeat
runs update them in place. Everything under `topics/` is an
[OKF v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
concept document, recording its sources, the release that wrote it, and who
approved it.

## Configuration

The defaults are meant to work untouched. To change one, set it in a TOML file
or in an environment variable named after it, upper-cased with a
`COMMONPLACE_` prefix — e.g. `COMMONPLACE_EDITOR="code --wait"`. Each source
overrides the ones below it:

1. environment variables
1. `.commonplace/config.toml` in your commonplace (seeded by `init`)
1. `~/.config/commonplace/config.toml` (the platform config dir)
1. the defaults below

`root` is the exception: it says where the per-repo file is, so it can only
come from `COMMONPLACE_ROOT`. An unknown key in either file is an error, so a
typo can't silently do nothing.

`commonplace config` prints the settings in effect once every source is
merged, as TOML you can paste into a config file; `commonplace config user`
prints just that one value.

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
`COMMONPLACE_UA` (or `ua`) to it — no need to wait for a release.
