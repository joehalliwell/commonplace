# Mélange Conversation Import Format

## Goal

To provide a standard, human-readable, and machine-parsable format for
conversation transcripts imported into the `melange` archive. The design
prioritizes simplicity and compatibility with standard Markdown tools.

## File Location

Files using this format reside within the hidden `.melange/imports/` directory
of your knowledge base. They are typically created by the `melange import`
command.

## Format Specification

The format consists of two main parts: a single file-level metadata block
(frontmatter) at the top, followed by the conversation turns, each demarcated by
a Markdown heading.

### File-Level Frontmatter (Required)

Every conversation file **must** begin with a YAML frontmatter block, delimited
by `---`. This block contains metadata for the entire conversation.

**Essential Fields:**
* `source_provider` (string): Where the conversation came from (e.g., `"Gemini
  Web UI"`, `"Claude Export"`, `"OpenAI API"`).
* `imported_at` (string): The ISO 8601 timestamp of when the file was imported.

**Recommended Optional Fields:**
* `participants` (list of strings): The names or roles of the participants
  (e.g., `[User, MelangeBot]`).
* `tags` (list of strings): Any tags for categorizing the conversation.

### Turn Delimiter & Content (Required)

Each turn in the conversation **must** be demarcated by a Level 2 Markdown
heading (`##`).

* The text immediately following the `##` is the **speaker's name or role**.
* All text content between one `##` heading and the next (or the end of the
  file) is the **content of that turn**. This content can be any standard
  Markdown.

### Per-Turn Metadata (Optional)

While the minimal format does not require it, the system supports adding
optional, structured metadata to individual turns.

* **For simple key-value data:** Use Dataview inline fields within the heading
  line: `## Speaker Name [key:: value]`.
* **For complex data:** Add a fenced YAML code block (` ```yaml `) immediately
  after the heading.

## Examples

### Example 1: The Ultra-Minimal Format

This is the baseline format. It contains only the required elements.

```markdown
---
source: "Claude"
imported_at: "2025-06-08T13:05:00Z"
---

# Conversation [from:: 2025-02-18]

## User [sent:: 2025-06-08T13:09:15Z]
What is the simplest way to represent a conversation?

## Claude [sent:: 2025-06-08T13:09:15Z]
Probably using Markdown headings to separate speakers. It's readable and uses the structure of the document itself.

## User
Okay, that makes sense.
```

### Example 2: An Enriched Format

This shows how the minimal format can be gracefully enhanced with optional
metadata.

````markdown
---
source_provider: "Melange"
imported_at: "2025-06-08T13:10:00Z"
participants: [Human, Melange]
tags: [self-reflection, design]
---

# Self-Reflection on Design Choices

## Human [sent:: 2025-06-08T13:09:15Z]
So, what are the core principles of this format?

# Melange [sent:: 2025-06-08T13:09:45Z]
```yaml
model: gpt-4o-2024-05-13
tokens: { prompt: 50, completion: 150 }
```
The principles are human-readability and ecosystem compatibility. The format
should feel natural inside a standard Markdown editor, leveraging headings for
structure, while providing optional, structured metadata for tooling.
````
