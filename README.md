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

#### Metadata Enrichment

- Automatic topic/tag extraction during import
- Track which conversations were particularly valuable
- Mark insights and key takeaways

#### Reflection & Review

- Periodic review commands to surface recent conversations
- Pattern detection: highlight recurring topics or questions
- Weekly/monthly digest generation

#### Knowledge Connections

- Automatic linking of related conversations
- Track how thinking evolves on a topic over time
- Identify knowledge gaps and follow-up opportunities

#### Synthesis & Sharing

- Combine insights from multiple conversations on a topic
- Create derived notes from conversation threads
- Export curated collections with privacy controls

#### Growth Tracking

- Visualize learning trajectories over time
- Track questions asked vs topics explored
- Revisit old conversations with new context

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

## Design Notes

- **Commonplace is an abstraction on top of git, not a git wrapper.** Commands like `init()` and `sync()` are part of the commonplace abstraction. The `git` command is an escape hatch for raw access.

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Format code
uv run ruff format .

# Type check
uv run mypy src/
```
