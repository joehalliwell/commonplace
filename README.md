# Commonplace

A personal knowledge management tool for archiving and organizing your AI conversations into a searchable digital commonplace book.

## What is Commonplace?

Commonplace transforms your scattered AI chat exports into an organized, searchable personal knowledge repository. Just like the traditional [commonplace books](https://en.wikipedia.org/wiki/Commonplace_book) used by scholars and thinkers throughout history, this tool helps you preserve and revisit your most valuable AI conversations.

## Features

### Current Capabilities
- **Import conversations** from multiple AI providers:
  - Claude (via ZIP export from claude.ai)
  - Gemini (via Google Takeout HTML export)
- **Standardized storage** as organized markdown files with metadata
- **Date-based organization** in a clear directory structure:
  ```
  ~/commonplace/
  ├── claude/2024/06/2024-06-28-conversation-title.md
  ├── gemini/2024/06/2024-06-28-gemini-conversations.md
  └── ...
  ```
- **Rich markdown format** with frontmatter, timestamps, and proper formatting

### Planned Features
- Interactive curation tools (move, rename, label)
- Conversation summarization and synthesis
- Cross-conversation search and analysis
- Journal generation from conversation insights

## Installation

```bash
pip install uv
uv tool install commonplace
```

## Setup

Set your storage location:
```bash
export COMMONPLACE_ROOT=/path/to/your/commonplace
# or create a .env file with:
# COMMONPLACE_ROOT=/path/to/your/commonplace
```

## Usage

### Import Claude conversations
1. Export your conversations from claude.ai (Download > Export)
2. Import the ZIP file:
```bash
commonplace import path/to/claude-export.zip
```

### Import Gemini conversations  
1. Request your data from [Google Takeout](https://takeout.google.com) (select "Gemini Apps")
2. Import the ZIP file:
```bash
commonplace import path/to/takeout-export.zip
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

## Philosophy

In the age of AI assistance, our conversations with AI systems often contain valuable insights, creative ideas, and learning moments. Commonplace ensures these digital dialogues don't disappear into the ether, but instead become part of your growing personal knowledge base—ready to be searched, referenced, and built upon.