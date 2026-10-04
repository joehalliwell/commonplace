import json
import shutil
import subprocess
from pathlib import Path

import pytest

from commonplace._import._commands import import_
from commonplace._repo import Commonplace, _hash_file
from commonplace._utils import load_frontmatter

SAMPLE_EXPORTS_DIR = Path(__file__).parent / "resources" / "sample-exports"


@pytest.fixture
def sample_file(tmp_path):
    """Create a simple text file for blob storage tests."""
    p = tmp_path / "sample.txt"
    p.write_text("hello world")
    return p


def test_store_blob_copies_file(test_repo, sample_file):
    """File appears at .commonplace/blobs/<hash>/<name> and the next commit includes it."""
    repo_path = test_repo.store_blob(sample_file)

    digest = _hash_file(sample_file)
    expected_rel = Path(".commonplace") / "blobs" / digest / "sample.txt"
    assert repo_path.path == expected_rel

    abs_path = test_repo.root / expected_rel
    assert abs_path.exists()
    assert abs_path.read_text() == "hello world"

    test_repo.commit("Store blob", auto_index=False)
    tracked = subprocess.run(
        ["git", "-C", test_repo.root, "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    assert expected_rel.as_posix() in tracked.splitlines()


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


def test_store_blob_creates_gitattributes(test_repo, sample_file):
    """store_blob() ensures .gitattributes exists with LFS config."""
    gitattributes = test_repo.root / ".gitattributes"
    # Remove if init() already created it
    if gitattributes.exists():
        gitattributes.unlink()

    test_repo.store_blob(sample_file)

    assert gitattributes.exists()
    content = gitattributes.read_text()
    assert ".commonplace/blobs/**" in content
    assert "filter=lfs" in content


def test_init_creates_gitattributes(tmp_path):
    """Commonplace.init() includes .gitattributes with LFS config."""
    root = tmp_path / "fresh_repo"
    root.mkdir()
    Commonplace.init(root)

    gitattributes = root / ".gitattributes"
    assert gitattributes.exists()
    content = gitattributes.read_text()
    assert ".commonplace/blobs/**" in content
    assert "filter=lfs" in content


def test_init_creates_claude_settings(tmp_path):
    """Commonplace.init() includes .claude/settings.json with marketplace config."""
    root = tmp_path / "fresh_repo"
    root.mkdir()
    Commonplace.init(root)

    settings = root / ".claude" / "settings.json"
    assert settings.exists()
    data = json.loads(settings.read_text())
    assert "commonplace" in data["extraKnownMarketplaces"]
    assert data["enabledPlugins"]["commonplace-skills@commonplace"] is True


def test_import_records_provenance(test_repo, tmp_path):
    """Imported markdown files contain source_export in frontmatter."""
    sample_dir = SAMPLE_EXPORTS_DIR / "claude.zip"
    export_path = tmp_path / "claude.zip"
    shutil.make_archive(str(export_path.with_suffix("")), "zip", sample_dir)

    import_(export_path, test_repo, user="Human")

    md_files = sorted((test_repo.root / "chats").glob("**/*.md"))
    assert len(md_files) > 0

    for md_file in md_files:
        metadata, _ = load_frontmatter(md_file.read_text())
        assert isinstance(metadata.get("source_export"), str), f"Missing source_export in {md_file}"


def test_import_provenance_points_to_valid_blob(test_repo, tmp_path):
    """The source_export path actually exists in the repo."""
    sample_dir = SAMPLE_EXPORTS_DIR / "claude.zip"
    export_path = tmp_path / "claude.zip"
    shutil.make_archive(str(export_path.with_suffix("")), "zip", sample_dir)

    import_(export_path, test_repo, user="Human")

    md_files = sorted((test_repo.root / "chats").glob("**/*.md"))
    assert len(md_files) > 0

    metadata, _ = load_frontmatter(md_files[0].read_text())
    blob_abs = test_repo.root / metadata["source_export"]
    assert blob_abs.exists(), f"Blob not found at {blob_abs}"


def test_import_stores_only_the_member_it_reads(test_repo, tmp_path):
    """Import stores conversations.json, not the users.json that only marks the ZIP as Claude's."""
    sample_dir = SAMPLE_EXPORTS_DIR / "claude.zip"
    export_path = tmp_path / "claude.zip"
    shutil.make_archive(str(export_path.with_suffix("")), "zip", sample_dir)

    import_(export_path, test_repo, user="Human")

    blobs_dir = test_repo.root / ".commonplace" / "blobs"
    blob_names = {f.name for f in blobs_dir.rglob("*") if f.is_file()}
    assert blob_names == {"conversations.json"}

    md_files = sorted((test_repo.root / "chats").glob("**/*.md"))
    metadata, _ = load_frontmatter(md_files[0].read_text())
    assert Path(metadata["source_export"]).name == "conversations.json"
