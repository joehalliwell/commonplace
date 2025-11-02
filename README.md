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

## Usage

### Import Claude conversations

1. Export your conversations from claude.ai (Download > Export)
1. Import the ZIP file:

```bash
commonplace import path/to/claude-export.zip
```

### Import Gemini conversations

1. Request your data from [Google Takeout](https://takeout.google.com)
1. Select "My Activity" and "Assistant"
1. Import the ZIP file:

```bash
commonplace import path/to/takeout-export.zip
```

### Import ChatGPT conversations

1. Export your data from ChatGPT (Settings > Data Controls > Export)
1. Import the ZIP file:

```bash
commonplace import path/to/chatgpt-export.zip
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
