"""Tests for repository commit functionality."""

import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

from commonplace._marginalia import marginalia_path
from commonplace._repo import Commonplace, GitError
from commonplace._show import links
from commonplace._types import Note
from commonplace._utils import load_frontmatter
from tests.porcelain import git


def test_commit_initial_changes(test_repo, make_note):
    """Test committing the first change to a new repository."""
    test_repo.put(make_note("test.md", "# Test\nHello world"))
    test_repo.commit("Initial commit")

    assert _git(test_repo, "log", "-1", "--format=%s") == "Initial commit\n"


def test_commit_no_changes(test_repo, make_note):
    """Test that committing with no changes does nothing."""
    test_repo.put(make_note("test.md", "# Test\nHello world"))
    test_repo.commit("Initial commit")

    first_commit_id = _head(test_repo)
    test_repo.commit("Should not create commit")

    assert _head(test_repo) == first_commit_id


def test_remove_committed_note_is_gone_from_head(test_repo, make_note):
    note = make_note("memory/claude/gone.md", "# Gone\n")
    test_repo.put(note)
    test_repo.commit("Add")

    test_repo.remove(note.path)
    test_repo.commit("Remove")

    assert not (test_repo.root / "memory/claude/gone.md").exists()
    assert "memory/claude" not in _git(test_repo, "ls-tree", "--name-only", "HEAD", "memory/").split()


def test_commit_subsequent_changes(test_repo, make_note):
    """Test committing changes after initial commit."""
    test_repo.put(make_note("test1.md", "# Test 1\nFirst note"))
    test_repo.commit("Initial commit")
    first_commit_id = _head(test_repo)

    test_repo.put(make_note("test2.md", "# Test 2\nSecond note"))
    test_repo.commit("Add second note")

    assert _head(test_repo) != first_commit_id
    assert _git(test_repo, "log", "-1", "--format=%s") == "Add second note\n"


def test_commit_modified_file(test_repo, make_note):
    """Test committing modifications to an existing file."""
    test_repo.put(make_note("test.md", "# Test\nOriginal content"))
    test_repo.commit("Initial commit")
    first_commit_id = _head(test_repo)

    test_repo.put(make_note("test.md", "# Test\nModified content"))
    test_repo.commit("Update note")

    assert _head(test_repo) != first_commit_id
    assert _git(test_repo, "log", "-1", "--format=%s") == "Update note\n"


def test_save_note_with_metadata_loads_back_unchanged(test_repo):
    note = Note(Path("test.md"), body="# Test\n\nHello: world\n", metadata={"gem": "Research: notes #1"})

    test_repo.put(note)

    assert test_repo.get(Path("test.md")) == note


def test_load_file_with_frontmatter_separates_metadata_from_body(test_repo):
    (test_repo.root / "test.md").write_text("---\ntags: [a, b]\n---\n\n# Test\n")

    note = test_repo.get(Path("test.md"))

    assert (note.metadata, note.body) == ({"tags": ["a", "b"]}, "# Test\n")


def test_load_file_opening_with_a_rule_is_all_body(test_repo):
    text = "---\n\nSome prose.\n\n---\n\nMore prose.\n"
    (test_repo.root / "test.md").write_text(text)

    note = test_repo.get(Path("test.md"))
    test_repo.put(note)

    assert (note.metadata, note.body) == ({}, text)
    assert (test_repo.root / "test.md").read_text() == text


def test_a_notes_version_follows_later_commits(test_repo, make_note):
    """A note's version tracks its committed content, even after HEAD moves on.

    The path -> content map is cached, so this is really a test that the cache is keyed
    on HEAD: everything downstream (incremental indexing, pruning, hiding deleted hits
    from search) decides what is current by comparing versions.
    """
    test_repo.put(make_note("test.md", "# Test\nOriginal content"))
    test_repo.commit("Add note")
    original = test_repo.content_ids()[Path("test.md")]

    test_repo.put(make_note("test.md", "# Test\nModified content"))
    test_repo.commit("Update note")
    modified = test_repo.content_ids()[Path("test.md")]

    assert original == _head(test_repo, "HEAD~1:test.md")
    assert modified == _head(test_repo, "HEAD:test.md")


def test_a_notes_version_after_a_merge_is_the_side_branchs_content(test_repo, make_note):
    """A file last changed on a merged side branch has that branch's content, not the mainline's before it."""
    test_repo.put(make_note("topic.md", "# Topic\n"))
    test_repo.commit("Add topic")
    _git(test_repo, "switch", "-q", "-c", "side")
    (test_repo.root / "topic.md").write_text("# Topic, revised\n")
    _git(test_repo, "commit", "-qam", "Revise topic")
    side = _head(test_repo, "HEAD:topic.md")
    _git(test_repo, "switch", "-q", "main")
    (test_repo.root / "other.md").write_text("# Other\n")
    _git(test_repo, "add", "other.md")
    _git(test_repo, "commit", "-qm", "Add other")
    _git(test_repo, "merge", "-q", "--no-ff", "-m", "Merge side", "side")

    assert test_repo.content_ids()[Path("topic.md")] == side


def test_note_paths_commonplace_dir_excluded(test_repo, make_note):
    """Skill-managed state under .commonplace/ is never a note."""
    test_repo.put(make_note("notes/idea.md", "# Idea\n"))
    test_repo.put(make_note(".commonplace/skills/rake/chaff.md", "# Chaff\n"))
    test_repo.commit("Add notes")

    assert list(test_repo.note_paths()) == [Path("index.md"), Path("notes/idea.md")]


def test_paths_includes_files_that_are_not_markdown(test_repo):
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
    test_repo.put(make_note("notes/idea.md", "# Idea\n"))
    test_repo.put(make_note(".claude/copy.md", "# Copy\n"))
    test_repo.put(make_note("notes/.hidden/draft.md", "# Draft\n"))
    test_repo.commit("Add notes")

    assert list(test_repo.note_paths()) == [Path("index.md"), Path("notes/idea.md")]


def test_open_subdirectory_of_repo_raises(test_repo):
    """A root inside a repo is a mistake, not a request for the repo around it."""

    with pytest.raises(ValueError, match="not the root"):
        Commonplace.open(test_repo.root / "notes")


def test_config_reads_repo_file(tmp_path, monkeypatch):
    """A setting in the repo's own .commonplace/config.toml reaches repo.config."""
    monkeypatch.delenv("COMMONPLACE_USER", raising=False)
    Commonplace.init(tmp_path)
    (tmp_path / ".commonplace" / "config.toml").write_text('user = "Ada"\n')

    assert Commonplace.open(tmp_path).config.user == "Ada"


def test_index_matches_head_after_commit(test_repo, make_note):
    """Test that index tree matches HEAD tree after commit (not previous HEAD)."""
    test_repo.put(make_note("test.md", "# Test\nOriginal content"))
    test_repo.commit("Initial commit")

    test_repo.put(make_note("test.md", "# Test\nModified content"))
    test_repo.commit("Update note")

    # Staged differences from HEAD would look like a revert.
    assert _git(test_repo, "diff", "--cached", "--name-only") == ""


def test_commit_never_indexes(test_repo, index_spy, make_note):
    """Indexing reads what was committed, so it runs after a command, never inside the storage layer."""
    test_repo.put(make_note("test.md", "# Test\nHello world"))
    test_repo.commit("Test commit")

    assert index_spy == []


def test_init_seeds_a_root_index_declaring_okf_version(test_repo):
    """The bundle root has no parent to describe it, so init writes its index.md."""
    metadata, _ = load_frontmatter((test_repo.root / "index.md").read_text())

    assert metadata["okf_version"] == "0.2"


def test_init_creates_every_folder_the_root_index_links(test_repo):
    """A fresh repo has the folders its root index describes, so no link needs excusing."""
    assert test_repo.check() == []


def test_init_scaffolds_mdformat_that_preserves_wikilinks(test_repo):
    """Formatting with the scaffolded config leaves root-relative and bare wikilinks unescaped."""
    note = test_repo.root / "note.md"
    note.write_text("See [[/chats/a/b]] and [[foam]].\n")

    subprocess.run([sys.executable, "-m", "mdformat", "note.md"], cwd=test_repo.root, check=True)

    assert note.read_text() == "See [[/chats/a/b]] and [[foam]].\n"


def test_init_scaffolds_mdformat_hook_with_wikilink_that_skips_blobs(test_repo):
    """The pre-commit hook needs the plugin installed, and must not touch content-addressed blobs."""
    config = yaml.safe_load((test_repo.root / ".pre-commit-config.yaml").read_text())
    hook = next(hook for repo in config["repos"] for hook in repo["hooks"] if hook["id"] == "mdformat")

    assert "mdformat-wikilink" in hook["additional_dependencies"]
    assert re.search(hook["exclude"], ".commonplace/blobs/ab/cd/note.md")
    assert not re.search(hook["exclude"], "notes/ideas.md")


def _git(repo: Commonplace, *args: str) -> str:
    """Act as a second writer on the same checkout."""
    return git(repo.root, *args)


def _head(repo: Commonplace, rev: str = "HEAD") -> str:
    return _git(repo, "rev-parse", rev).strip()


def _hook(repo: Commonplace, script: str) -> None:
    hook = repo.root / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\n" + script)
    hook.chmod(0o755)


def test_commit_concurrent_writer_keeps_their_commit(test_repo, make_note):
    """A commit landing while a journal is open survives ours, in HEAD and in the index."""
    journal = Path("journal/2026/10/2026-10-01.md")
    (test_repo.root / "x.md").write_text("# X\n")
    _git(test_repo, "add", "x.md")
    _git(test_repo, "commit", "-m", "Concurrent writer")

    test_repo.put(Note(journal, "# Journal\n"))
    test_repo.commit("Update journal entry")

    assert "x.md" in _git(test_repo, "ls-tree", "--name-only", "HEAD").split()
    assert _git(test_repo, "status", "--porcelain") == ""
    assert _git(test_repo, "diff", "--name-only", "HEAD~1", "HEAD").split() == ["journal/2026/10/2026-10-01.md"]


def test_commit_unrelated_changes_left_uncommitted(test_repo, make_note):
    """Only what the operation saved is committed: another writer's edits, staged or not, stay theirs."""
    for name in ("draft.md", "staged.md"):
        (test_repo.root / name).write_text("# Original\n")
    _git(test_repo, "add", "draft.md", "staged.md")
    _git(test_repo, "commit", "-m", "Seed")
    (test_repo.root / "draft.md").write_text("# Half-written\n")
    (test_repo.root / "staged.md").write_text("# Half-written\n")
    _git(test_repo, "add", "staged.md")

    test_repo.put(make_note("journal.md", "# Journal\n"))
    test_repo.commit("Update journal entry")

    assert _git(test_repo, "diff", "--name-only", "HEAD~1", "HEAD").split() == ["journal.md"]
    assert _git(test_repo, "status", "--porcelain").splitlines() == [" M draft.md", "M  staged.md"]


def test_commit_awkward_filenames_committed_verbatim(test_repo, make_note):
    """Spaces, non-ASCII and glob characters are names, not syntax."""
    names = ["chats/gemini/2026/10/2026-10-01-مرحبا بالعالم.md", "notes/[draft] *.md"]
    for name in names:
        test_repo.put(make_note(name, "# Note\n"))
    test_repo.commit("Add notes")

    changed = _git(test_repo, "-c", "core.quotePath=false", "diff", "--name-only", "HEAD~1", "HEAD")
    assert sorted(changed.splitlines()) == sorted(names)
    assert _git(test_repo, "status", "--porcelain") == ""


def test_commit_hook_reformats_retries_with_hook_output(test_repo, make_note):
    """A pre-commit hook that rewrites our file and fails is a formatter: re-stage and go again."""
    _hook(test_repo, "grep -q messy note.md || exit 0\nsed -i s/messy/tidy/ note.md\nexit 1\n")

    test_repo.put(make_note("note.md", "# messy\n"))
    test_repo.commit("Add note")

    assert _git(test_repo, "show", "HEAD:note.md") == "# tidy\n"
    assert _git(test_repo, "status", "--porcelain") == ""


def test_commit_hook_reformats_back_to_head_is_nothing_to_commit(test_repo, make_note):
    """Re-importing a note the hook already formatted changes nothing once the hook has had its say."""
    _hook(test_repo, "grep -q messy note.md || exit 0\nsed -i s/messy/tidy/ note.md\nexit 1\n")
    test_repo.put(make_note("note.md", "# messy\n"))
    test_repo.commit("Add note")
    head = _head(test_repo)

    test_repo.put(make_note("note.md", "# messy\n"))
    test_repo.commit("Re-import note")

    assert _head(test_repo) == head
    assert _git(test_repo, "status", "--porcelain") == ""


def test_commit_hook_rejects_raises_with_hook_output(test_repo, make_note):
    """A hook that fails without touching anything is a real objection, so it reaches the user."""
    _hook(test_repo, "echo 'lint says no' >&2\nexit 1\n")
    head = _git(test_repo, "rev-parse", "HEAD")

    test_repo.put(make_note("note.md", "# Note\n"))
    with pytest.raises(GitError, match="lint says no"):
        test_repo.commit("Add note")

    assert _git(test_repo, "rev-parse", "HEAD") == head
    assert (test_repo.root / "note.md").read_text() == "# Note\n"


def test_commit_index_briefly_locked_waits_and_succeeds(test_repo, make_note):
    lock = test_repo.root / ".git" / "index.lock"
    lock.touch()
    threading.Timer(0.3, lock.unlink).start()

    test_repo.put(make_note("note.md", "# Note\n"))
    test_repo.commit("Add note")

    assert _git(test_repo, "log", "-1", "--format=%s") == "Add note\n"


def test_commit_index_locked_too_long_raises_and_leaves_index(test_repo, make_note, monkeypatch):
    monkeypatch.setattr("commonplace._repo._LOCK_RETRY_DELAYS", (0.01, 0.01))
    index = test_repo.root / ".git" / "index"
    before = index.read_bytes()
    (test_repo.root / ".git" / "index.lock").touch()

    test_repo.put(make_note("note.md", "# Note\n"))
    with pytest.raises(GitError, match=r"index\.lock"):
        test_repo.commit("Add note")

    assert index.read_bytes() == before


# --- The repository as a graph ------------------------------------------------

IDEAS, OTHER = Path("notes/ideas.md"), Path("notes/other.md")


def _write(repo: Commonplace, files: dict[Path, str]) -> None:
    for path, text in files.items():
        (repo.root / path).parent.mkdir(parents=True, exist_ok=True)
        (repo.root / path).write_text(text)


def test_a_notes_labels_are_its_own_tags_then_its_marginalias(test_repo):
    _write(
        test_repo,
        {
            IDEAS: "---\ntags:\n- tea\n---\n# Ideas\n",
            marginalia_path(IDEAS): "---\nmarginalia: 1\ntags:\n- hidden\n- tea\n---\n",
        },
    )

    assert test_repo.get(IDEAS).labels == ["tea", "hidden"]


def test_an_edge_in_marginalia_is_written_in_their_file_and_lands_from_the_note(test_repo):
    """The second body is a file of its own, so that's where the edge is; the edge is the note's, so it lands from it."""
    _write(
        test_repo,
        {
            IDEAS: "# Ideas\n",
            OTHER: "# Other\n",
            marginalia_path(IDEAS): "---\nmarginalia: 1\n---\n\n- see [the other](other.md)\n",
        },
    )

    [edge] = test_repo.get(IDEAS).edges

    assert (edge.link.source, edge.link.line) == (marginalia_path(IDEAS), 5)
    assert test_repo.files.lands(edge) == [OTHER]


def test_a_note_labelled_hidden_in_its_own_frontmatter_is_left_out_of_links(test_repo):
    _write(test_repo, {IDEAS: "See [[other]].\n", OTHER: "---\ntags: [hidden]\n---\n# Other\n"})

    assert links(test_repo, IDEAS) == []
    assert [neighbour.other for neighbour in links(test_repo, IDEAS, include_hidden=True)] == ["/notes/other"]


def test_a_notes_provenance_is_an_edge_to_its_archive_and_a_missing_one_is_broken(test_repo, tmp_path):
    """What a chat's text quotes makes no edge, but the archive it was rendered from does."""
    capture = tmp_path / "claude-wire.jsonl.gz"
    capture.write_bytes(b"captured")
    archive = test_repo.store_blob(capture).path
    kept, lost = Path("chats/claude/2026/01/kept.md"), Path("chats/claude/2026/01/lost.md")
    gone = ".commonplace/blobs/0000/gone-wire.jsonl.gz"
    _write(
        test_repo,
        {
            kept: f"---\nsource: claude\nsource_export: {archive.as_posix()}\n---\n\nQuoted: [[nothing]].\n",
            lost: f"---\nsource: claude\nsource_export: {gone}\n---\n",
        },
    )

    assert [(found.link.source, found.link.target) for found in test_repo.check()] == [(lost, gone)]
    assert [note.path for note, _ in test_repo.into(archive)] == [kept]


def test_blobs_committed_in_storage_order_then_uncommitted_by_path(test_repo, tmp_path):
    for name in ("b.json", "a.json", "d.json", "c.json"):
        (tmp_path / name).write_text(name)
    committed = []
    for name in ("b.json", "a.json"):
        committed.append(test_repo.store_blob(tmp_path / name).path)
        test_repo.commit(f"Store {name}")
        test_repo.put(Note(Path(f"{name}.md"), "# Note\n"))
        test_repo.commit(f"Note {name}")
    pending = sorted((test_repo.store_blob(tmp_path / name).path for name in ("d.json", "c.json")), key=Path.as_posix)

    assert [blob.path for blob in test_repo.blobs()] == [*committed, *pending]
    assert [blob.path.name for blob in test_repo.blobs("a.json", "c.json")] == ["a.json", "c.json"]


def test_uncommitted_reports_edited_deleted_and_untracked_under_pathspec(test_repo):
    _write(test_repo, {Path(name): "# Seed\n" for name in ("notes/edited.md", "notes/deleted.md", "other.md")})
    _git(test_repo, "add", ".")
    _git(test_repo, "commit", "-m", "Seed")
    (test_repo.root / "notes/edited.md").write_text("# Edited\n")
    (test_repo.root / "notes/deleted.md").unlink()
    (test_repo.root / "notes/new.md").write_text("# New\n")
    (test_repo.root / "other.md").write_text("# Elsewhere\n")

    assert test_repo.uncommitted("notes") == {"notes/edited.md", "notes/deleted.md", "notes/new.md"}


def test_a_notes_version_is_its_committed_content_so_a_reverted_edit_restores_it(test_repo):
    """An index keyed by content re-reads only what changed, however many commits pass."""
    note = Path("notes/tea.md")
    versions = []
    for text in ("# Tea\n", "# Tea, brewed\n", "# Tea\n"):
        _write(test_repo, {note: text})
        test_repo.commit("Edit tea", written=[note.as_posix()])
        versions.append(test_repo.content_ids()[note])

    assert versions[0] == versions[2] != versions[1]


def test_an_uncommitted_note_has_no_version(test_repo):
    _write(test_repo, {Path("notes/draft.md"): "# Draft\n"})

    assert Path("notes/draft.md") not in test_repo.content_ids()


def test_moved_maps_each_renamed_path_to_where_its_last_occupant_is_now(test_repo):
    """A chain of moves ends where the file is now; a path reused after a move follows its latest occupant."""
    _write(test_repo, {Path(name): f"# {name}\nenough words to be recognised as the same file\n" for name in "ab"})
    _git(test_repo, "add", ".")
    _git(test_repo, "commit", "-m", "Seed")
    for old, new in [("a", "x"), ("x", "y"), ("b", "z")]:
        _git(test_repo, "mv", old, new)
        _git(test_repo, "commit", "-m", f"Move {old}")
    _write(test_repo, {Path("a"): "# a again\nan unrelated file that reuses the name of the first\n"})
    _git(test_repo, "add", "a")
    _git(test_repo, "commit", "-m", "Reuse a")
    _git(test_repo, "mv", "a", "w")
    _git(test_repo, "commit", "-m", "Move a again")

    assert test_repo.moved() == {Path("a"): Path("w"), Path("x"): Path("y"), Path("b"): Path("z")}
