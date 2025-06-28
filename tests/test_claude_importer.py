import json
import tempfile
from pathlib import Path
from zipfile import ZipFile
from datetime import datetime
from commonplace._claude import ClaudeImporter
from commonplace._types import Role


class TestClaudeImporter:
    def create_test_zipfile(self, conversations_data, users_data=None):
        """Helper to create a test zipfile with Claude data."""
        if users_data is None:
            users_data = [{"id": "user1", "name": "Test User"}]

        temp_file = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        with ZipFile(temp_file.name, "w") as zf:
            zf.writestr("conversations.json", json.dumps(conversations_data))
            zf.writestr("users.json", json.dumps(users_data))
        return Path(temp_file.name)

    def test_can_import_valid_claude_zip(self):
        conversations = [{"uuid": "123", "name": "Test", "created_at": "2024-01-01T12:00:00Z", "chat_messages": []}]
        zip_path = self.create_test_zipfile(conversations)

        try:
            importer = ClaudeImporter()
            assert importer.can_import(zip_path) is True
        finally:
            zip_path.unlink()

    def test_can_import_invalid_zip(self):
        # Create a zip without required files
        temp_file = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        with ZipFile(temp_file.name, "w") as zf:
            zf.writestr("other.json", "{}")

        try:
            importer = ClaudeImporter()
            assert importer.can_import(Path(temp_file.name)) is False
        finally:
            Path(temp_file.name).unlink()

    def test_can_import_non_zip_file(self):
        temp_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        temp_file.write(b"not a zip file")
        temp_file.close()

        try:
            importer = ClaudeImporter()
            assert importer.can_import(Path(temp_file.name)) is False
        finally:
            Path(temp_file.name).unlink()

    def test_import_basic_conversation(self):
        conversations = [
            {
                "uuid": "test-123",
                "name": "Test Conversation",
                "created_at": "2024-01-01T12:00:00Z",
                "chat_messages": [
                    {
                        "sender": "human",
                        "created_at": "2024-01-01T12:00:00Z",
                        "content": [{"type": "text", "text": "Hello"}],
                    },
                    {
                        "sender": "assistant",
                        "created_at": "2024-01-01T12:00:01Z",
                        "content": [{"type": "text", "text": "Hi there!"}],
                    },
                ],
            }
        ]

        zip_path = self.create_test_zipfile(conversations)

        try:
            importer = ClaudeImporter()
            logs = importer.import_(zip_path)

            assert len(logs) == 1
            log = logs[0]

            assert log.source == "claude"
            assert log.title == "Test Conversation"
            assert log.metadata["uuid"] == "test-123"
            assert len(log.messages) == 2

            # Check first message
            msg1 = log.messages[0]
            assert msg1.sender == Role.USER
            assert msg1.content == "Hello"

            # Check second message
            msg2 = log.messages[1]
            assert msg2.sender == Role.ASSISTANT
            assert msg2.content == "Hi there!"
        finally:
            zip_path.unlink()

    def test_import_with_non_text_content(self):
        conversations = [
            {
                "uuid": "test-123",
                "name": "Test",
                "created_at": "2024-01-01T12:00:00Z",
                "chat_messages": [
                    {
                        "sender": "human",
                        "created_at": "2024-01-01T12:00:00Z",
                        "content": [
                            {"type": "text", "text": "Here's some text"},
                            {"type": "image", "url": "https://example.com/image.jpg"},
                            {"type": "text", "text": "More text"},
                        ],
                    }
                ],
            }
        ]

        zip_path = self.create_test_zipfile(conversations)

        try:
            importer = ClaudeImporter()
            logs = importer.import_(zip_path)

            message = logs[0].messages[0]
            content_lines = message.content.split("\n")

            assert "Here's some text" in content_lines
            assert "More text" in content_lines
            assert any("Skipped content of type image" in line for line in content_lines)
        finally:
            zip_path.unlink()

    def test_to_log_conversion(self):
        importer = ClaudeImporter()
        thread_data = {
            "uuid": "test-uuid",
            "name": "Test Thread",
            "created_at": "2024-01-01T12:00:00Z",
            "chat_messages": [],
        }

        log = importer._to_log(thread_data)

        assert log.source == "claude"
        assert log.title == "Test Thread"
        assert log.metadata["uuid"] == "test-uuid"
        assert isinstance(log.created, datetime)

    def test_to_message_conversion(self):
        importer = ClaudeImporter()
        message_data = {
            "sender": "human",
            "created_at": "2024-01-01T12:00:00Z",
            "content": [{"type": "text", "text": "Test message"}],
        }

        message = importer._to_message(message_data)

        assert message.sender == Role.USER
        assert message.content == "Test message"
        assert isinstance(message.created, datetime)
