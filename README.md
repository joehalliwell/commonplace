# Commonplace

A personal knowledge management tool for archiving and organizing your AI
conversations into a searchable digital commonplace book.

## What is Commonplace?

Commonplace transforms your scattered AI chat exports into an organized,
searchable personal knowledge repository. Just like the traditional [commonplace
books](https://en.wikipedia.org/wiki/Commonplace_book) used by scholars and
thinkers throughout history, this tool helps you preserve and revisit your most
valuable AI conversations.

## Features

### Current Capabilities

- **Import conversations** from multiple AI providers:
  - Claude (via ZIP export from claude.ai)
  - Gemini (via Google Takeout HTML export)
  - ChatGPT (via ZIP export)
- **Standardized storage** as organized markdown files with metadata
- **Date-based organization** in a clear directory structure:
  ```
  ~/commonplace/
  ├── chats/                    # AI conversations (imported by tool)
  │   ├── claude/2024/06/2024-06-28-conversation-title.md
  │   ├── gemini/2024/06/2024-06-28-gemini-conversations.md
  │   └── ...
  ├── journal/                  # Manual journal entries
  └── notes/                    # Manual notes and thoughts
  ```
- **Rich markdown format** with frontmatter, timestamps, and proper formatting
- **Git integration** for change tracking and automatic commits when importing conversations
- **Semantic search** using vector embeddings to find relevant conversations by meaning
- **Full-text search** and **hybrid search** combining semantic and keyword matching

### Planned Features

- Interactive curation tools (move, rename, label)
- Advanced synthesis across both imported chats and manual content

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

2. Initialize your commonplace as a git repository (recommended):
```bash
commonplace init
```

This creates a git repository for change tracking and enables automatic commits when importing conversations.

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
2. Import the ZIP file:
```bash
commonplace import path/to/claude-export.zip
```

### Import Gemini conversations
1. Request your data from [Google Takeout](https://takeout.google.com)
2. Select "My Activity" and "Assistant"
3. Import the ZIP file:
```bash
commonplace import path/to/takeout-export.zip
```

### Import ChatGPT conversations
1. Export your data from ChatGPT (Settings > Data Controls > Export)
2. Import the ZIP file:
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

## Output Format

Each conversation is stored as a markdown file with:

- **Frontmatter metadata** (source, timestamps, IDs)
- **Structured headers** for each speaker
- **Preserved formatting** and content
- **Date-based organization** for easy browsing

Example output:
```markdown
---
model: claude-3-sonnet
uuid: conversation-123
---

# Exploring Machine Learning [created:: 2024-06-28T14:30:00]

## Human [created:: 2024-06-28T14:30:00]
Can you explain how neural networks work?

## Claude [created:: 2024-06-28T14:30:15]
Neural networks are computational models inspired by biological brains...
```

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Format code  
uv run ruff format .

# Type check
uv run mypy src/
```
