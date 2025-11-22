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

This creates a git repository for change tracking and enables automatic commits
when importing conversations.

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
