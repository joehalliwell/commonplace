"""Tests for repository commit functionality."""

import json
from contextlib import closing
from datetime import UTC
from pathlib import Path

from commonplace._repo import Commonplace
from commonplace._types import Note, RepoPath


def test_commit_initial_changes(test_repo, make_note):
    """Test committing the first change to a new repository."""
    test_repo.save(make_note("test.md", "# Test\nHello world"))
    test_repo.commit("Initial commit")

    assert not test_repo.git.head_is_unborn
    assert test_repo.git.head.peel().message == "Initial commit"


def test_commit_no_changes(test_repo, make_note):
    """Test that committing with no changes does nothing."""
    test_repo.save(make_note("test.md", "# Test\nHello world"))
    test_repo.commit("Initial commit")

    first_commit_id = test_repo.git.head.target
    test_repo.commit("Should not create commit")

    assert test_repo.git.head.target == first_commit_id


def test_remove_committed_note_is_gone_from_head(test_repo, make_note):
    note = make_note("memory/claude/gone.md", "# Gone\n")
    test_repo.save(note)
    test_repo.commit("Add", auto_index=False)

    test_repo.remove(note.repo_path.path)
    test_repo.commit("Remove", auto_index=False)

    assert not (test_repo.root / "memory/claude/gone.md").exists()
    assert "memory" not in test_repo.git.head.peel().tree


def test_commit_subsequent_changes(test_repo, make_note):
    """Test committing changes after initial commit."""
    test_repo.save(make_note("test1.md", "# Test 1\nFirst note"))
    test_repo.commit("Initial commit")
    first_commit_id = test_repo.git.head.target

    test_repo.save(make_note("test2.md", "# Test 2\nSecond note"))
    test_repo.commit("Add second note")

    assert test_repo.git.head.target != first_commit_id
    assert test_repo.git.head.peel().message == "Add second note"


def test_commit_modified_file(test_repo, make_note):
    """Test committing modifications to an existing file."""
    test_repo.save(make_note("test.md", "# Test\nOriginal content"))
    test_repo.commit("Initial commit")
    first_commit_id = test_repo.git.head.target

    test_repo.save(make_note("test.md", "# Test\nModified content"))
    test_repo.commit("Update note")

    assert test_repo.git.head.target != first_commit_id
    assert test_repo.git.head.peel().message == "Update note"


def test_save_note_with_metadata_loads_back_unchanged(test_repo):
    repo_path = RepoPath(path=Path("test.md"), ref="")
    note = Note(repo_path=repo_path, body="# Test\n\nHello: world\n", metadata={"gem": "Research: notes #1"})

    test_repo.save(note)

    assert test_repo.load(repo_path) == note


def test_load_file_with_frontmatter_separates_metadata_from_body(test_repo):
    (test_repo.root / "test.md").write_text("---\ntags: [a, b]\n---\n\n# Test\n")

    note = test_repo.load(RepoPath(path=Path("test.md"), ref=""))

    assert (note.metadata, note.body) == ({"tags": ["a", "b"]}, "# Test\n")


def test_load_file_opening_with_a_rule_is_all_body(test_repo):
    text = "---\n\nSome prose.\n\n---\n\nMore prose.\n"
    (test_repo.root / "test.md").write_text(text)

    note = test_repo.load(RepoPath(path=Path("test.md"), ref=""))
    test_repo.save(note)

    assert (note.metadata, note.body) == ({}, text)
    assert (test_repo.root / "test.md").read_text() == text


def test_make_repo_path_follows_later_commits(test_repo, make_note):
    """A note's ref tracks the commit that last modified it, even after HEAD moves on.

    The path -> commit map is cached, so this is really a test that the cache is keyed
    on HEAD: everything downstream (incremental indexing, pruning, hiding deleted hits
    from search) decides what is current by comparing refs.
    """
    test_repo.save(make_note("test.md", "# Test\nOriginal content"))
    test_repo.commit("Add note", auto_index=False)
    original = test_repo.make_repo_path("test.md")

    test_repo.save(make_note("test.md", "# Test\nModified content"))
    test_repo.commit("Update note", auto_index=False)
    modified = test_repo.make_repo_path("test.md")

    assert original.ref == str(test_repo.git.head.peel().parents[0].id)
    assert modified.ref == str(test_repo.git.head.target)


def test_note_paths_commonplace_dir_excluded(test_repo, make_note):
    """Skill-managed state under .commonplace/ is never a note."""
    test_repo.save(make_note("notes/idea.md", "# Idea\n"))
    test_repo.save(make_note(".commonplace/skills/rake/chaff.md", "# Chaff\n"))
    test_repo.commit("Add notes", auto_index=False)

    assert [p.path for p in test_repo.note_paths()] == [Path("notes/idea.md")]


def test_paths_includes_files_that_are_not_markdown(test_repo):
    (test_repo.root / "notes").mkdir()
    (test_repo.root / "notes" / "idea.md").write_text("# Idea\n")
    (test_repo.root / "notes" / "sketch.png").write_bytes(b"")

    assert {Path("notes/idea.md"), Path("notes/sketch.png")} <= set(test_repo.paths())


def test_paths_gitignored_files_excluded(test_repo):
    with open(test_repo.root / ".gitignore", "a") as fd:
        fd.write("scratch/\n")
    (test_repo.root / "scratch").mkdir()
    (test_repo.root / "scratch" / "draft.md").write_text("# Draft\n")

    assert not [path for path in test_repo.paths() if path.parts[0] == "scratch"]


def test_note_paths_dot_dirs_excluded(test_repo, make_note):
    """No dot-directory is descended, at any depth."""
    test_repo.save(make_note("notes/idea.md", "# Idea\n"))
    test_repo.save(make_note(".claude/copy.md", "# Copy\n"))
    test_repo.save(make_note("notes/.hidden/draft.md", "# Draft\n"))
    test_repo.commit("Add notes", auto_index=False)

    assert [p.path for p in test_repo.note_paths()] == [Path("notes/idea.md")]


def test_config_reads_repo_file(tmp_path, monkeypatch):
    """A setting in the repo's own .commonplace/config.toml reaches repo.config."""
    monkeypatch.delenv("COMMONPLACE_USER", raising=False)
    Commonplace.init(tmp_path)
    (tmp_path / ".commonplace" / "config.toml").write_text('user = "Ada"\n')

    with closing(Commonplace.open(tmp_path)) as repo:
        assert repo.config.user == "Ada"


def test_index_matches_head_after_commit(test_repo, make_note):
    """Test that index tree matches HEAD tree after commit (not previous HEAD)."""
    from pygit2.enums import ObjectType

    test_repo.save(make_note("test.md", "# Test\nOriginal content"))
    test_repo.commit("Initial commit")

    test_repo.save(make_note("test.md", "# Test\nModified content"))
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


def test_commit_auto_indexes_by_default(test_repo, index_spy, make_note):
    """Test that commit auto-indexes when config.auto_index is True."""
    assert test_repo.config.auto_index is True

    test_repo.save(make_note("test.md", "# Test\nHello world"))
    test_repo.commit("Test commit")

    assert index_spy == [(test_repo, False)]


def test_commit_no_index_flag_disables_indexing(test_repo, index_spy, make_note):
    """Test that commit with auto_index=False doesn't index."""
    test_repo.save(make_note("test.md", "# Test\nHello world"))
    test_repo.commit("Test commit", auto_index=False)

    assert index_spy == []


def test_commit_index_flag_overrides_config(test_repo, index_spy, make_note, monkeypatch):
    """Test that auto_index=True overrides config when auto_index is False."""
    monkeypatch.setattr(test_repo.config, "auto_index", False)

    test_repo.save(make_note("test.md", "# Test\nHello world"))
    test_repo.commit("Test commit", auto_index=True)

    assert index_spy == [(test_repo, False)]


def test_commit_no_changes_skips_indexing(test_repo, index_spy, make_note):
    """Test that commit with no changes doesn't trigger indexing."""
    test_repo.save(make_note("test.md", "# Test\nHello world"))
    test_repo.commit("Initial commit")
    index_spy.clear()

    test_repo.commit("No changes")

    assert index_spy == []


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


def test_doctor_reports_a_managed_file_that_differs(test_repo):
    """A repo behind the current template is told so — and left exactly as it was."""
    gitignore = test_repo.root / ".gitignore"
    gitignore.write_text("# Mine\nsecrets/\n")

    report = test_repo.doctor()

    assert report.actions == []
    assert len(report.warnings) == 1
    assert ".gitignore" in report.warnings[0]
    assert gitignore.read_text() == "# Mine\nsecrets/\n"


def test_doctor_shows_the_diff_against_the_template(test_repo):
    """The diff is the whole point: it says what the template has that the repo doesn't."""
    gitattributes = test_repo.root / ".gitattributes"
    gitattributes.write_text("*.md text\n")

    report = test_repo.doctor()

    warning = next(w for w in report.warnings if ".gitattributes" in w)
    assert "-.commonplace/blobs/** filter=lfs diff=lfs merge=lfs -text" in warning
    assert "+*.md text" in warning


def test_doctor_reports_additions_too(test_repo):
    """Any difference gets shown; deciding which side is right is the reader's job."""
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


def test_doctor_reports_a_broken_link(test_repo):
    """A reference that lands nowhere is exactly what doctor is for."""
    (test_repo.root / "notes").mkdir()
    (test_repo.root / "notes" / "note.md").write_text("See [the other one](gone.md).\n")

    report = test_repo.doctor()

    warning = next(w for w in report.warnings if "notes/note.md" in w)
    assert "gone.md" in warning


def test_doctor_suggests_where_a_renamed_target_went(test_repo):
    """The dominant failure is a rename, so say where the file went."""
    (test_repo.root / "notes" / "moved").mkdir(parents=True)
    (test_repo.root / "notes" / "moved" / "target.md").write_text("# Target\n")
    (test_repo.root / "notes" / "note.md").write_text("See [it](target.md).\n")

    report = test_repo.doctor()

    warning = next(w for w in report.warnings if "notes/note.md" in w)
    assert "notes/moved/target.md" in warning


def test_doctor_reports_a_link_to_a_gitignored_file(test_repo):
    """A link that resolves only on this machine is dead for anyone who clones."""
    with open(test_repo.root / ".gitignore", "a") as fd:
        fd.write("scratch/\n")
    (test_repo.root / "scratch").mkdir()
    (test_repo.root / "scratch" / "draft.md").write_text("# Draft\n")
    (test_repo.root / "notes").mkdir()
    (test_repo.root / "notes" / "note.md").write_text("See [the draft](../scratch/draft.md).\n")

    report = test_repo.doctor()

    warning = next(w for w in report.warnings if "notes/note.md" in w)
    assert "scratch/draft.md" in warning


def test_doctor_is_quiet_when_links_resolve(test_repo):
    """No warning for a repo whose links are all good."""
    (test_repo.root / "notes").mkdir()
    (test_repo.root / "notes" / "target.md").write_text("# Target\n")
    (test_repo.root / "notes" / "note.md").write_text("See [it](target.md).\n")

    report = test_repo.doctor()

    assert not any("note.md" in warning for warning in report.warnings)


def test_doctor_groups_broken_links_by_file(test_repo):
    """One warning per file, however many links in it are broken."""
    (test_repo.root / "notes").mkdir()
    (test_repo.root / "notes" / "note.md").write_text("[a](gone-a.md)\n\n[b](gone-b.md)\n")

    report = test_repo.doctor()

    warnings = [w for w in report.warnings if "notes/note.md" in w]
    assert len(warnings) == 1
    assert "gone-a.md" in warnings[0]
    assert "gone-b.md" in warnings[0]


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
