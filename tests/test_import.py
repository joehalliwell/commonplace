import shutil
from collections import namedtuple
from datetime import datetime
from pathlib import Path

import pytest

from commonplace._import._commands import MarkdownSerializer, import_
from commonplace._import._types import ActivityLog, Message, Role

SampleExport = namedtuple("SampleExport", ["name", "path"])

SAMPLE_EXPORTS_DIR = Path(__file__).parent / "resources" / "sample-exports"
SAMPLE_EXPORTS = [f.name for f in SAMPLE_EXPORTS_DIR.iterdir()]


@pytest.fixture(scope="module", params=SAMPLE_EXPORTS)
def sample_export(request, tmp_path_factory):
    name = request.param
    tmp_path = tmp_path_factory.mktemp(name)
    zipfile = shutil.make_archive(tmp_path / name, "zip", SAMPLE_EXPORTS_DIR / name)
    return SampleExport(name, zipfile)


def test_import(sample_export, test_repo, snapshot):
    import_(sample_export.path, test_repo, user="Human")

    buffer = ""
    for path in sorted((test_repo.root / "chats").glob("**/*.md")):
        buffer += f"<!-- Contents of {path.relative_to(test_repo.root).as_posix()} -->\n"
        buffer += open(path, "r").read() + "\n"

    snapshot.assert_match(buffer, "outputs.md")


def test_serialize_log(snapshot):
    """Test basic serialization of ActivityLog to markdown."""
    serializer = MarkdownSerializer(human="Human", assistant="Assistant")

    messages = [
        Message(
            sender=Role.USER,
            content="Hello",
            created=datetime(2024, 1, 1, 12, 0, 0),
            metadata={"id": "message-0"},
        ),
        Message(
            sender=Role.ASSISTANT,
            content="Hi there!",
            created=datetime(2024, 1, 1, 12, 0, 1),
            metadata={"id": "message-1"},
        ),
    ]

    log = ActivityLog(
        source="test",
        title="Test Chat",
        created=datetime(2024, 1, 1, 12, 0, 0),
        messages=messages,
        metadata={"id": "log-0"},
    )

    result = serializer.serialize(log)
    snapshot.assert_match(result, "log.md")
