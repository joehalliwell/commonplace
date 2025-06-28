from datetime import datetime
from unittest.mock import Mock

from commonplace._journal import JournalGenerator
from commonplace._store import ActivityLogDirectoryStore


def test_conversation_stats_empty(tmp_path):
    """Test stats with no conversations."""
    store = ActivityLogDirectoryStore(root=tmp_path)
    mock_model = Mock()
    journal_gen = JournalGenerator(store, mock_model)

    stats = journal_gen.conversation_stats(7)

    assert stats["total_conversations"] == 0
    assert stats["days_analyzed"] == 7


def test_conversation_stats_with_files(tmp_path):
    """Test stats with actual conversation files."""
    store = ActivityLogDirectoryStore(root=tmp_path)
    mock_model = Mock()
    journal_gen = JournalGenerator(store, mock_model)

    # Use today's date for the test files
    today = datetime.now()
    year_month = f"{today.year}/{today.month:02d}"
    date_str = today.strftime("%Y-%m-%d")

    # Create test conversation files in proper nested structure
    claude_dir = tmp_path / "claude" / year_month
    claude_dir.mkdir(parents=True, exist_ok=True)

    gemini_dir = tmp_path / "gemini" / year_month
    gemini_dir.mkdir(parents=True, exist_ok=True)

    # Create files with today's date
    claude_file = claude_dir / f"{date_str}-test-conversation.md"
    claude_file.write_text("# Test conversation")

    gemini_file = gemini_dir / f"{date_str}-gemini-chat.md"
    gemini_file.write_text("# Gemini chat")

    stats = journal_gen.conversation_stats(7)

    assert stats["total_conversations"] == 2
    assert stats["days_analyzed"] == 7


def test_recent_conversations_summary_with_llm_error(tmp_path):
    """Test summary generation when LLM fails."""
    store = ActivityLogDirectoryStore(root=tmp_path)
    # Use a mock model that raises an exception
    mock_model = Mock()
    mock_model.prompt.side_effect = Exception("Model unavailable")
    journal_gen = JournalGenerator(store, mock_model)

    # Use today's date for the test file
    today = datetime.now()
    year_month = f"{today.year}/{today.month:02d}"
    date_str = today.strftime("%Y-%m-%d")

    # Create a test conversation file in proper structure
    claude_dir = tmp_path / "claude" / year_month
    claude_dir.mkdir(parents=True, exist_ok=True)

    claude_file = claude_dir / f"{date_str}-test.md"
    claude_file.write_text("# Test")

    # This should raise an exception since the model fails
    try:
        _summary = journal_gen.recent_conversations_summary(7)
        assert False, "Expected exception to be raised"
    except Exception as e:
        assert "Model unavailable" in str(e)


def test_recent_conversations_no_conversations(tmp_path):
    """Test summary when no conversations exist."""
    store = ActivityLogDirectoryStore(root=tmp_path)
    mock_model = Mock()
    # Mock a response for when there are no files
    mock_response = Mock()
    mock_response.text.return_value = "No recent conversations found."
    mock_model.prompt.return_value = mock_response
    journal_gen = JournalGenerator(store, mock_model)

    summary = journal_gen.recent_conversations_summary(7)

    assert "No recent conversations found" in summary
