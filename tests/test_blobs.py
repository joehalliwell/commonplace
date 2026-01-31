import shutil
from pathlib import Path

import pytest

from commonplace._import._commands import import_
from commonplace._repo import _hash_file
from commonplace._utils import parse_frontmatter

SAMPLE_EXPORTS_DIR = Path(__file__).parent / "resources" / "sample-exports"


@pytest.fixture
def sample_file(tmp_path):
    """Create a simple text file for blob storage tests."""
    p = tmp_path / "sample.txt"
    p.write_text("hello world")
    return p


def test_store_blob_copies_file(test_repo, sample_file):
    """File appears at .commonplace/blobs/<hash>/<name> and is staged."""
    repo_path = test_repo.store_blob(sample_file)

    digest = _hash_file(sample_file)
    expected_rel = Path(".commonplace") / "blobs" / digest / "sample.txt"
    assert repo_path.path == expected_rel

    abs_path = test_repo.root / expected_rel
    assert abs_path.exists()
    assert abs_path.read_text() == "hello world"

    # Check it's staged in the git index
    status = test_repo.git.status_file(expected_rel.as_posix())
    # INDEX_NEW means staged as a new file
    from pygit2.enums import FileStatus

    assert status & FileStatus.INDEX_NEW


def test_store_blob_is_idempotent(test_repo, sample_file):
    """Same file twice returns the same path, only one copy on disk."""
    path1 = test_repo.store_blob(sample_file)
    path2 = test_repo.store_blob(sample_file)
    assert path1.path == path2.path


def test_store_blob_different_content_different_hash(test_repo, tmp_path):
    """Two files with the same name but different content get different blob paths."""
    f1 = tmp_path / "a" / "data.bin"
    f1.parent.mkdir()
    f1.write_bytes(b"aaa")

    f2 = tmp_path / "b" / "data.bin"
    f2.parent.mkdir()
    f2.write_bytes(b"bbb")

    p1 = test_repo.store_blob(f1)
    p2 = test_repo.store_blob(f2)
    assert p1.path != p2.path
    assert p1.path.name == p2.path.name == "data.bin"


def test_import_records_provenance(test_repo, tmp_path):
    """Imported markdown files contain source_export in frontmatter."""
    sample_dir = SAMPLE_EXPORTS_DIR / "claude.zip"
    export_path = tmp_path / "claude.zip"
    shutil.make_archive(str(export_path.with_suffix("")), "zip", sample_dir)

    import_(export_path, test_repo, user="Human")

    md_files = sorted((test_repo.root / "chats").glob("**/*.md"))
    assert len(md_files) > 0

    for md_file in md_files:
        metadata, _ = parse_frontmatter(md_file.read_text())
        assert "source_export" in metadata, f"Missing source_export in {md_file}"


def test_import_provenance_points_to_valid_blob(test_repo, tmp_path):
    """The source_export path actually exists in the repo."""
    sample_dir = SAMPLE_EXPORTS_DIR / "claude.zip"
    export_path = tmp_path / "claude.zip"
    shutil.make_archive(str(export_path.with_suffix("")), "zip", sample_dir)

    import_(export_path, test_repo, user="Human")

    md_files = sorted((test_repo.root / "chats").glob("**/*.md"))
    assert len(md_files) > 0

    metadata, _ = parse_frontmatter(md_files[0].read_text())
    blob_rel = metadata["source_export"]
    blob_abs = test_repo.root / blob_rel
    assert blob_abs.exists(), f"Blob not found at {blob_abs}"
