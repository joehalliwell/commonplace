"""Tests for repository commit functionality."""

import json
from datetime import UTC
from pathlib import Path

from commonplace._types import Note, RepoPath


def test_commit_initial_changes(test_repo):
    """Test committing the first change to a new repository."""
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Initial commit")

    assert not test_repo.git.head_is_unborn
    assert test_repo.git.head.peel().message == "Initial commit"


def test_commit_no_changes(test_repo):
    """Test that committing with no changes does nothing."""
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Initial commit")

    first_commit_id = test_repo.git.head.target
    test_repo.commit("Should not create commit")

    assert test_repo.git.head.target == first_commit_id


def test_commit_subsequent_changes(test_repo):
    """Test committing changes after initial commit."""
    note1 = Note(
        repo_path=RepoPath(path=Path("test1.md"), ref=""),
        content="# Test 1\nFirst note",
    )
    test_repo.save(note1)
    test_repo.commit("Initial commit")
    first_commit_id = test_repo.git.head.target

    note2 = Note(
        repo_path=RepoPath(path=Path("test2.md"), ref=""),
        content="# Test 2\nSecond note",
    )
    test_repo.save(note2)
    test_repo.commit("Add second note")

    assert test_repo.git.head.target != first_commit_id
    assert test_repo.git.head.peel().message == "Add second note"


def test_commit_modified_file(test_repo):
    """Test committing modifications to an existing file."""
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nOriginal content",
    )
    test_repo.save(note)
    test_repo.commit("Initial commit")
    first_commit_id = test_repo.git.head.target

    modified_note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nModified content",
    )
    test_repo.save(modified_note)
    test_repo.commit("Update note")

    assert test_repo.git.head.target != first_commit_id
    assert test_repo.git.head.peel().message == "Update note"


def test_index_matches_head_after_commit(test_repo):
    """Test that index tree matches HEAD tree after commit (not previous HEAD)."""
    from pygit2.enums import ObjectType

    # First commit
    note1 = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nOriginal content",
    )
    test_repo.save(note1)
    test_repo.commit("Initial commit")

    # Second commit modifies the file
    note2 = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nModified content",
    )
    test_repo.save(note2)
    test_repo.commit("Update note")

    # Reload index from disk (simulates what happens in a new command/process)
    test_repo.git.index.read()

    # After commit, the index tree should match the HEAD tree
    # If they don't match, git will show staged changes (looks like a revert)
    index_tree_id = test_repo.git.index.write_tree()
    head_commit = test_repo.git.head.peel(ObjectType.COMMIT)
    head_tree_id = head_commit.tree.id

    assert index_tree_id == head_tree_id, (
        f"Index tree {index_tree_id} doesn't match HEAD tree {head_tree_id}. "
        "This makes it look like there are staged changes (a revert)!"
    )


def test_has_remote_exists(test_repo):
    """Test has_remote returns True when remote exists."""
    test_repo.git.remotes.create("origin", "https://github.com/test/repo.git")
    assert test_repo.has_remote("origin")


def test_has_remote_not_exists(test_repo):
    """Test has_remote returns False when remote doesn't exist."""
    assert not test_repo.has_remote("origin")


def test_has_remote_custom_name(test_repo):
    """Test has_remote works with custom remote names."""
    test_repo.git.remotes.create("upstream", "https://github.com/test/repo.git")
    assert test_repo.has_remote("upstream")
    assert not test_repo.has_remote("origin")


def test_commit_auto_indexes_by_default(test_repo, monkeypatch):
    """Test that commit auto-indexes when config.auto_index is True."""
    # Track if index was called
    index_called = []

    def mock_index(repo, rebuild):
        index_called.append((repo, rebuild))

    # Patch the index function
    import commonplace._search._commands

    monkeypatch.setattr(commonplace._search._commands, "index", mock_index)

    # Ensure config has auto_index=True (default)
    assert test_repo.config.auto_index is True

    # Create and commit a note
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Test commit")

    # Verify index was called once with rebuild=False
    assert len(index_called) == 1
    assert index_called[0] == (test_repo, False)


def test_commit_no_index_flag_disables_indexing(test_repo, monkeypatch):
    """Test that commit with auto_index=False doesn't index."""
    # Track if index was called
    index_called = []

    def mock_index(repo, rebuild):
        index_called.append((repo, rebuild))

    # Patch the index function
    import commonplace._search._commands

    monkeypatch.setattr(commonplace._search._commands, "index", mock_index)

    # Create and commit a note with auto_index=False
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Test commit", auto_index=False)

    # Verify index was NOT called
    assert len(index_called) == 0


def test_commit_index_flag_overrides_config(test_repo, monkeypatch):
    """Test that auto_index=True overrides config when auto_index is False."""
    # Track if index was called
    index_called = []

    def mock_index(repo, rebuild):
        index_called.append((repo, rebuild))

    # Patch the index function
    import commonplace._search._commands

    monkeypatch.setattr(commonplace._search._commands, "index", mock_index)

    # Set config to auto_index=False
    monkeypatch.setattr(test_repo.config, "auto_index", False)

    # Create and commit a note with auto_index=True (override)
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Test commit", auto_index=True)

    # Verify index WAS called (flag overrode config)
    assert len(index_called) == 1
    assert index_called[0] == (test_repo, False)


def test_commit_no_changes_skips_indexing(test_repo, monkeypatch):
    """Test that commit with no changes doesn't trigger indexing."""
    # Track if index was called
    index_called = []

    def mock_index(repo, rebuild):
        index_called.append((repo, rebuild))

    # Patch the index function
    import commonplace._search._commands

    monkeypatch.setattr(commonplace._search._commands, "index", mock_index)

    # Create initial commit
    note = Note(
        repo_path=RepoPath(path=Path("test.md"), ref=""),
        content="# Test\nHello world",
    )
    test_repo.save(note)
    test_repo.commit("Initial commit")

    # Clear the tracking
    index_called.clear()

    # Try to commit with no changes
    test_repo.commit("No changes")

    # Verify index was NOT called (no changes means no commit means no index)
    assert len(index_called) == 0


def test_doctor_restores_every_file_init_creates(test_repo):
    """Whatever init() lays down, doctor() puts back — no drift between the two."""
    scaffolding = sorted(entry.path for entry in test_repo.git.index)
    assert scaffolding, "init() should have staged some scaffolding"

    for path in scaffolding:
        (test_repo.root / path).unlink()

    test_repo.doctor()

    assert [p for p in scaffolding if not (test_repo.root / p).exists()] == []


def test_doctor_creates_missing_gitignore(test_repo):
    """doctor() restores a deleted .gitignore, cache entry and all."""
    gitignore = test_repo.root / ".gitignore"
    gitignore.unlink()

    report = test_repo.doctor()

    assert any(".gitignore" in action for action in report.actions)
    assert ".commonplace/cache" in gitignore.read_text()


def test_doctor_creates_missing_config(test_repo):
    """doctor() restores a deleted .commonplace/config.toml."""
    config = test_repo.root / ".commonplace" / "config.toml"
    config.unlink()

    report = test_repo.doctor()

    assert any("config.toml" in action for action in report.actions)
    assert config.exists()


def test_doctor_creates_missing_claude_settings(test_repo):
    """doctor() restores a deleted .claude/settings.json with the marketplace config."""
    settings = test_repo.root / ".claude" / "settings.json"
    settings.unlink()

    report = test_repo.doctor()

    assert any("settings.json" in action for action in report.actions)
    assert "commonplace" in json.loads(settings.read_text())["extraKnownMarketplaces"]


def test_doctor_warns_when_a_managed_file_is_modified(test_repo):
    """commonplace owns .gitignore, so an edit is reported — and left alone."""
    gitignore = test_repo.root / ".gitignore"
    gitignore.write_text("# Mine\nsecrets/\n")

    report = test_repo.doctor()

    assert report.actions == []
    assert len(report.warnings) == 1
    assert ".gitignore" in report.warnings[0]
    assert gitignore.read_text() == "# Mine\nsecrets/\n"


def test_doctor_shows_what_changed_in_a_managed_file(test_repo):
    """The warning carries a diff, so you can see whether the edit was deliberate."""
    gitattributes = test_repo.root / ".gitattributes"
    gitattributes.write_text("*.md text\n")

    report = test_repo.doctor()

    warning = next(w for w in report.warnings if ".gitattributes" in w)
    assert "-.commonplace/blobs/** filter=lfs diff=lfs merge=lfs -text" in warning
    assert "+*.md text" in warning


def test_doctor_warns_about_additions_to_managed_files(test_repo):
    """Even an addition is drift from the template: nothing in these files is hand-tuned."""
    gitignore = test_repo.root / ".gitignore"
    gitignore.write_text(gitignore.read_text() + "secrets/\n")

    report = test_repo.doctor()

    assert any("+secrets/" in warning for warning in report.warnings)


def test_doctor_warns_when_marketplace_config_is_removed(test_repo):
    """The plugin marketplace config is commonplace's; losing it should not be silent."""
    settings = test_repo.root / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": []}}))

    report = test_repo.doctor()

    assert any("settings.json" in warning for warning in report.warnings)


def test_doctor_ignores_edits_to_unmanaged_config(test_repo):
    """.commonplace/config.toml is yours to set — doctor only checks it exists."""
    config = test_repo.root / ".commonplace" / "config.toml"
    config.write_text('user = "Joe"\nwrap = 100\n')

    report = test_repo.doctor()

    assert report.warnings == []


def test_doctor_is_idempotent(test_repo):
    """doctor() reports nothing when everything is already in place."""
    test_repo.doctor()

    report = test_repo.doctor()

    assert report.actions == []
    assert report.warnings == []


def test_doctor_stages_what_it_creates(test_repo):
    """A recreated file lands in the on-disk index, so the next commit picks it up."""
    gitignore = test_repo.root / ".gitignore"
    gitignore.unlink()

    test_repo.doctor()
    test_repo.git.index.read()

    staged = test_repo.git[test_repo.git.index[".gitignore"].id].data.decode()
    assert staged == gitignore.read_text()


def test_last_commit_time_returns_none_on_missing_pathspec(test_repo):
    """A pathspec with no history in the repo yields None."""
    assert test_repo.last_commit_time("chats/claude/") is None


def test_last_commit_time_returns_utc_datetime_after_commit(test_repo):
    """The cursor is UTC whatever offset git reports the author date in."""

    (test_repo.root / "chats" / "claude" / "2026" / "07").mkdir(parents=True)
    note = test_repo.root / "chats" / "claude" / "2026" / "07" / "test.md"
    note.write_text("# test\n")
    test_repo.git.index.add(note.relative_to(test_repo.root).as_posix())
    test_repo.commit("Import test", auto_index=False)

    ts = test_repo.last_commit_time("chats/claude/")
    assert ts is not None
    assert ts.tzinfo is not None
    assert ts.utcoffset() == UTC.utcoffset(None)


def test_last_commit_time_ignores_rename_source_with_diff_filter(test_repo):
    """`git mv chats/foo chats/bar` should not poison the fetch cursor for
    chats/foo/ — with diff_filter='AM' we only see adds/modifications."""
    import subprocess

    chats = test_repo.root / "chats" / "claude" / "2026" / "07"
    chats.mkdir(parents=True)
    note = chats / "test.md"
    note.write_text("# test\n")
    test_repo.git.index.add(note.relative_to(test_repo.root).as_posix())
    test_repo.commit("Import test", auto_index=False)

    ts_before = test_repo.last_commit_time("chats/claude/", diff_filter="AM")
    assert ts_before is not None

    # Simulate a rename: mv all of chats/claude/ to chats/claude-old/
    subprocess.run(
        ["git", "-C", str(test_repo.root), "mv", "chats/claude", "chats/claude-old"],
        check=True,
    )
    test_repo.commit("Rename claude → claude-old", auto_index=False)

    # Without diff_filter, the rename commit *is* the last one touching
    # chats/claude/ — that's the bug we're guarding against.
    ts_touched = test_repo.last_commit_time("chats/claude/")
    assert ts_touched is not None
    assert ts_touched >= ts_before  # rename is newer

    # With diff_filter='AM', the rename commit is skipped (it deletes from
    # chats/claude/) so we see the earlier import commit.
    ts_am = test_repo.last_commit_time("chats/claude/", diff_filter="AM")
    assert ts_am == ts_before
