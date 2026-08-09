# Commonplace

A personal knowledge management tool for archiving and organizing your notes,
journal entries and AI conversations into a searchable digital archive.

Commonplace is named after the [commonplace
book](https://en.wikipedia.org/wiki/Commonplace_book) that scholars used in
antiquity.

## Features

### Current Capabilities

- 💬 **Import conversations** from multiple assistants:
  - Claude (via ZIP export from claude.ai)
  - Gemini (via Google Takeout HTML export)
  - ChatGPT (via ZIP export)
- 📁 **Standardized storage** as organized markdown files with metadata
- 🗂️ **Date-based organization** in a clear directory structure:
  ```
  ~/commonplace/
  ├── chats/                    # AI conversations (imported by tool)
  │   ├── claude/2024/06/2024-06-28-conversation-title.md
  │   ├── gemini/2024/06/2024-06-28-gemini-conversations.md
  │   └── ...
  ├── journal/                  # Manual journal entries
  └── notes/                    # Manual notes and thoughts
  ```
- ✨ **Rich markdown format** with frontmatter, timestamps, and proper formatting
- 🔄 **Git integration** for change tracking and automatic commits when importing conversations
- 🔍 **Full-text and semantic search** using vector embeddings to find relevant
  conversations by meaning

## Installation

```bash
pip install uv
uv tool install commonplace
```

## Setup

1. Set your storage location:

```bash
export COMMONPLACE_ROOT=/path/to/your/commonplace
# or create a .env file with:
# COMMONPLACE_ROOT=/path/to/your/commonplace
```

2. Initialize your commonplace:

```bash
commonplace init
```

This creates a git repository for change tracking, enables automatic commits
when importing conversations, and writes four config files:

| File                       | Purpose                                                     |
| -------------------------- | ----------------------------------------------------------- |
| `.commonplace/config.toml` | your settings — commonplace seeds it, then leaves it to you |
| `.gitignore`               | keeps the search index and editor cruft out of git          |
| `.gitattributes`           | tracks imported attachments with Git LFS                    |
| `.claude/settings.json`    | registers the Claude Code plugins below                     |

The last three are commonplace's to maintain; `commonplace doctor` will tell
you if they drift.

3. Configure an LLM for journal generation (optional):

```bash
# Install and configure OpenAI (or other providers)
llm install llm-openai
llm keys set openai
# Enter your API key when prompted

# Or use local models
llm install llm-gpt4all
```

## Exporting Conversations

Before you can import conversations into Commonplace, you need to export them from each service.

### Exporting from Claude

1. Go to [claude.ai](https://claude.ai)
1. Click your profile icon (bottom left)
1. Select **Settings**
1. Go to **Data & Privacy**
1. Click **Export data**
1. You'll receive an email with a download link (usually within a few minutes)
1. Download the ZIP file from the email link

### Exporting from ChatGPT

1. Go to [chat.openai.com](https://chat.openai.com)
1. Click your profile icon (bottom left)
1. Select **Settings**
1. Go to **Data controls**
1. Click **Export data**
1. Confirm the export request
1. You'll receive an email with a download link (can take up to 24 hours)
1. Download the ZIP file from the email link

### Exporting from Gemini

1. Go to [Google Takeout](https://takeout.google.com)
1. Click **Deselect all**
1. Scroll down and select **My Activity**
1. Click **Multiple formats** and ensure HTML is selected
1. Click **All activity data included** and select only **Assistant**
1. Click **Next step**
1. Choose delivery method (email link recommended)
1. Click **Create export**
1. You'll receive an email when ready (can take several hours)
1. Download the ZIP file from the email link

⚠️ **Note**: Export links are temporary and typically expire after 7 days.

## Usage

### Import conversations

Once you have exported your conversations (see [Exporting Conversations](#exporting-conversations) above), import them:

```bash
# Import any supported export format
commonplace import path/to/export.zip
```

The importer automatically detects the format (Claude, ChatGPT, or Gemini) and processes accordingly.

### Fetch conversations directly

Skip the export/download dance by pulling new conversations straight from
the provider:

```bash
# Fetch from all configured sources
commonplace fetch

# Restrict to a specific source
commonplace fetch --source claude
commonplace fetch --source gemini
commonplace fetch --source chatgpt
```

`fetch` reads your logged-in session cookies from Chrome — log in once in the
browser and the session lasts several weeks (Claude) or a few days (Gemini,
with auto-refresh). The incremental cursor is derived from git history (last
commit touching `chats/{source}/`), so subsequent runs only pull
conversations updated since the previous fetch.

**Supported sources:**

- `claude` — reads `claude.ai` session cookie, hits internal
  `/api/organizations/{org}/chat_conversations` endpoints. Notes land at
  `chats/claude/`.
- `gemini` — reads `gemini.google.com` session cookie (`__Secure-1PSID`),
  hits internal `batchexecute` RPCs. Extracts per-turn timestamps, Gem
  personas, and model thought traces — richer than the Google Takeout HTML
  export. Notes land at `chats/gemini/`.
- `chatgpt` — reads `chatgpt.com` session cookie, trades it for a bearer token
  at `/api/auth/session`, then walks `/backend-api/conversations`. Requests are
  paced: chatgpt.com is behind Cloudflare, which challenges bursts. Notes land
  at `chats/chatgpt/`.

Note: these use the providers' internal endpoints, which are unofficial and
may change without notice. If a fetcher stops working, fall back to the
manual export flow above.

**If a provider starts rejecting you as a bot.** Fetchers send a Chrome
User-Agent, because every provider fronts its internal API with a bot check
that a terse or stale one fails. The bundled default ages, so it can be
overridden without waiting for a release:

```bash
export COMMONPLACE_UA="Mozilla/5.0 (...) Chrome/999.0.0.0 Safari/537.36"
```

Copy the value from `navigator.userAgent` in your browser's console. It also
works as `ua` in `.commonplace/config.toml` (per repo) or the global config.

**Claude fetcher vs Takeout.** The Claude fetcher's data is a strict subset
of the manual export: Anthropic's internal conversation endpoint currently
strips `<antThinking>` blocks (visible in the manual export ZIP) from message
text server-side. If preserving Claude's thought-tag meta-reasoning matters
to you, keep using the manual export flow for the affected conversations.
See issue #6.

**Note on `gemini` vs `gemini-takeout`.** The Google Takeout importer
(retained for historical imports) now writes to `chats/gemini-takeout/`;
the fetcher owns `chats/gemini/`. If you previously imported Gemini history
from Takeout, migrate the old path before the first `fetch --source gemini`:

```bash
git -C $COMMONPLACE_ROOT mv chats/gemini chats/gemini-takeout
git -C $COMMONPLACE_ROOT commit -m "Migrate Takeout Gemini imports to gemini-takeout path"
```

### Search your conversations

Build a search index and query your conversations:

```bash
# Build the search index (run once, or after importing new conversations)
commonplace index

# Semantic search - finds content by meaning
commonplace search "explain neural networks"

# Full-text search - keyword matching only
commonplace search "explain neural networks" --method fts

# Hybrid search - combines both approaches (default)
commonplace search "explain neural networks" --method hybrid

# Limit number of results
commonplace search "machine learning" --limit 5

# Rebuild index from scratch
commonplace index --rebuild
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
```

### Check your repo

```bash
commonplace doctor
```

Restores any of the config files from [Setup](#setup) that have gone missing,
and warns about the managed ones you have edited — with a diff, so you can see
whether the change was deliberate. It never overwrites your edits.
