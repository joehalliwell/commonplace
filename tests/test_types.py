from datetime import datetime
from commonplace._types import ActivityLog, Message, Role


class TestMessage:
    def test_message_creation(self):
        msg = Message(sender=Role.USER, content="Hello world", created=datetime(2024, 1, 1, 12, 0, 0))
        assert msg.sender == Role.USER
        assert msg.content == "Hello world"
        assert msg.created == datetime(2024, 1, 1, 12, 0, 0)
        assert msg.metadata == {}

    def test_message_with_metadata(self):
        metadata = {"tokens": 42, "model": "gpt-4"}
        msg = Message(sender=Role.ASSISTANT, content="Response", created=datetime.now(), metadata=metadata)
        assert msg.metadata == metadata


class TestActivityLog:
    def test_activity_log_creation(self):
        messages = [
            Message(sender=Role.USER, content="Question", created=datetime(2024, 1, 1, 12, 0, 0)),
            Message(sender=Role.ASSISTANT, content="Answer", created=datetime(2024, 1, 1, 12, 0, 1)),
        ]

        log = ActivityLog(
            source="test", title="Test Conversation", created=datetime(2024, 1, 1, 12, 0, 0), messages=messages
        )

        assert log.source == "test"
        assert log.title == "Test Conversation"
        assert len(log.messages) == 2
        assert log.metadata == {}

    def test_activity_log_with_metadata(self):
        log = ActivityLog(
            source="claude", title="Test", created=datetime.now(), messages=[], metadata={"uuid": "12345"}
        )
        assert log.metadata["uuid"] == "12345"


class TestRole:
    def test_role_enum_values(self):
        assert Role.SYSTEM != Role.USER
        assert Role.USER != Role.ASSISTANT
        assert Role.ASSISTANT != Role.SYSTEM
