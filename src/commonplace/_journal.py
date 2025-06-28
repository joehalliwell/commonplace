"""
Journal generation and conversation analysis using LLMs.

Provides functionality to summarize, analyze, and generate insights
from imported AI conversations.
"""

from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path

import llm

from commonplace import logger
from commonplace._store import ActivityLogDirectoryStore


class JournalGenerator:
    """Generates journal entries and insights from conversation archives."""

    def __init__(self, store: ActivityLogDirectoryStore, model: llm.Model) -> None:
        """
        Initialize journal generator.

        Args:
            store: ActivityLogDirectoryStore for reading conversations
            model_name: LLM model to use (must be configured in llm)
        """
        self.store = store
        self.model = model

    def recent_conversations_summary(self, days: int = 7) -> str:
        """
        Generate a summary of recent conversations.

        Args:
            days: Number of days to look back

        Returns:
            Summary text of recent conversations
        """
        # Get conversations from the last N days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        recent_files = self.store.fetch(start_date, end_date)

        if not recent_files:
            logger.info(f"No conversations found in the last {days} days.")

        # Generate AI summary of the content
        recent_content = self._extract_conversation_snippets(recent_files)
        ai_summary = self._generate_ai_summary(recent_content, days)
        return ai_summary

    def _extract_conversation_snippets(self, files: list[Path], max_chars: int = 20_000) -> str:
        """Extract key snippets from conversation files for AI summarization."""
        snippets = []
        for file_path in files:
            content = open(file_path).read()
            if len(content) > 20000:
                logger.info(f"Truncating {file_path} to {max_chars} chars")
                content = content[:20000]
            snippets.extend([f"--- <!- from {file_path} -->", "", content, ""])
        return "\\n".join(snippets)

    def _get_prompt(self, name) -> str:
        return resources.read_text("commonplace.resources", name, encoding="utf-8")

    def _generate_ai_summary(self, content: str, days: int) -> str:
        """Generate AI summary of conversation content."""
        prompt = self._get_prompt("gemini.txt").format(content=content, days=days)

        try:
            response = self.model.prompt(prompt)
            return response.text()
        except Exception as e:
            logger.warning(f"Failed to generate AI summary: {e}")
            raise

    def conversation_stats(self, days: int = 30) -> dict[str, int]:
        """
        Get statistics about conversations.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with conversation statistics
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        files = self.store.fetch(start_date, end_date)

        stats = {
            "total_conversations": len(files),
            "days_analyzed": days,
        }

        return stats
