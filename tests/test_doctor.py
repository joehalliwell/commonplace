"""Tests for `doctor`: its operations, how they are selected, and what each reports."""

import json
import logging

from commonplace._doctor import doctor
from tests.porcelain import git


def test_doctor_restores_every_file_init_creates(test_repo):
    """Whatever init() lays down, doctor() puts back — no drift between the two."""
    scaffolding = git(test_repo.root, "ls-files").splitlines()
    assert scaffolding, "init() should have staged some scaffolding"

    for path in scaffolding:
        (test_repo.root / path).unlink()

    doctor(test_repo)

    assert [p for p in scaffolding if not (test_repo.root / p).exists()] == []


def test_doctor_creates_missing_gitignore(test_repo):
    """doctor() restores a deleted .gitignore, cache entry and all."""
    gitignore = test_repo.root / ".gitignore"
    gitignore.unlink()

    report = doctor(test_repo)

    assert any(".gitignore" in action for action in report.actions)
    assert ".commonplace/cache" in gitignore.read_text()


def test_doctor_creates_missing_config(test_repo):
    """doctor() restores a deleted .commonplace/config.toml."""
    config = test_repo.root / ".commonplace" / "config.toml"
    config.unlink()

    report = doctor(test_repo)

    assert any("config.toml" in action for action in report.actions)
    assert config.exists()


def test_doctor_creates_missing_claude_settings(test_repo):
    """doctor() restores a deleted .claude/settings.json with the marketplace config."""
    settings = test_repo.root / ".claude" / "settings.json"
    settings.unlink()

    report = doctor(test_repo)

    assert any("settings.json" in action for action in report.actions)
    assert "commonplace" in json.loads(settings.read_text())["extraKnownMarketplaces"]


def test_doctor_shows_the_plugin_hint_only_after_restoring_claude_settings(test_repo):
    (test_repo.root / ".gitignore").unlink()
    other = doctor(test_repo)
    (test_repo.root / ".claude" / "settings.json").unlink()

    settings = doctor(test_repo)

    assert not any("/plugin" in action for action in other.actions)
    assert any("/plugin marketplace add" in action for action in settings.actions)


def test_doctor_is_quiet_on_a_fresh_repo(test_repo):
    """The root index links directories a fresh repo doesn't have yet; that isn't breakage."""
    report = doctor(test_repo)

    assert report.warnings == []


def test_doctor_leaves_an_edited_root_index_alone(test_repo):
    """Once seeded, the root index.md is the user's."""
    index = test_repo.root / "index.md"
    index.write_text("# Mine\n")

    report = doctor(test_repo)

    assert report.warnings == []
    assert index.read_text() == "# Mine\n"


def test_doctor_reports_a_managed_file_that_differs(test_repo):
    """A repo behind the current template is told so — and left exactly as it was."""
    gitignore = test_repo.root / ".gitignore"
    gitignore.write_text("# Mine\nsecrets/\n")

    report = doctor(test_repo)

    assert report.actions == []
    assert len(report.warnings) == 1
    assert ".gitignore" in report.warnings[0]
    assert gitignore.read_text() == "# Mine\nsecrets/\n"


def test_doctor_shows_the_diff_against_the_template(test_repo):
    """The diff is the whole point: it says what the template has that the repo doesn't."""
    gitattributes = test_repo.root / ".gitattributes"
    gitattributes.write_text("*.md text\n")

    report = doctor(test_repo)

    warning = next(w for w in report.warnings if ".gitattributes" in w)
    assert "-.commonplace/blobs/** filter=lfs diff=lfs merge=lfs -text" in warning
    assert "+*.md text" in warning


def test_doctor_reports_additions_too(test_repo):
    """Any difference gets shown; deciding which side is right is the reader's job."""
    gitignore = test_repo.root / ".gitignore"
    gitignore.write_text(gitignore.read_text() + "secrets/\n")

    report = doctor(test_repo)

    assert any("+secrets/" in warning for warning in report.warnings)


def test_doctor_warns_when_marketplace_config_is_removed(test_repo):
    """The plugin marketplace config is commonplace's; losing it should not be silent."""
    settings = test_repo.root / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": []}}))

    report = doctor(test_repo)

    assert any("settings.json" in warning for warning in report.warnings)


def test_doctor_reports_mdformat_config_without_wikilink(test_repo):
    """Without the extension listed, mdformat escapes wikilinks even with the plugin installed."""
    mdformat_toml = test_repo.root / ".mdformat.toml"
    mdformat_toml.write_text(mdformat_toml.read_text().replace('    "wikilink",\n', ""))

    report = doctor(test_repo)

    warning = next(w for w in report.warnings if ".mdformat.toml" in w)
    assert '-    "wikilink",' in warning


def test_doctor_ignores_edits_to_unmanaged_config(test_repo):
    """.commonplace/config.toml is yours to set — doctor only checks it exists."""
    config = test_repo.root / ".commonplace" / "config.toml"
    config.write_text('user = "Joe"\nwrap = 100\n')

    report = doctor(test_repo)

    assert report.warnings == []


def test_doctor_reports_a_broken_link(test_repo):
    """A reference that lands nowhere is exactly what doctor is for."""
    (test_repo.root / "notes" / "note.md").write_text("See [the other one](gone.md).\n")

    report = doctor(test_repo)

    warning = next(w for w in report.warnings if "notes/note.md" in w)
    assert "gone.md" in warning


def test_doctor_suggests_where_a_renamed_target_went(test_repo):
    """The dominant failure is a rename, so say where the file went."""
    (test_repo.root / "notes" / "moved").mkdir(parents=True)
    (test_repo.root / "notes" / "moved" / "target.md").write_text("# Target\n")
    (test_repo.root / "notes" / "note.md").write_text("See [it](target.md).\n")

    report = doctor(test_repo)

    warning = next(w for w in report.warnings if "notes/note.md" in w)
    assert "notes/moved/target.md" in warning


def test_doctor_reports_a_link_to_a_gitignored_file(test_repo):
    """A link that resolves only on this machine is dead for anyone who clones."""
    with open(test_repo.root / ".gitignore", "a") as fd:
        fd.write("scratch/\n")
    (test_repo.root / "scratch").mkdir()
    (test_repo.root / "scratch" / "draft.md").write_text("# Draft\n")
    (test_repo.root / "notes" / "note.md").write_text("See [the draft](../scratch/draft.md).\n")

    report = doctor(test_repo)

    warning = next(w for w in report.warnings if "notes/note.md" in w)
    assert "scratch/draft.md" in warning


def test_doctor_is_quiet_when_links_resolve(test_repo):
    """No warning for a repo whose links are all good."""
    (test_repo.root / "notes" / "target.md").write_text("# Target\n")
    (test_repo.root / "notes" / "note.md").write_text("See [it](target.md).\n")

    report = doctor(test_repo)

    assert not any("note.md" in warning for warning in report.warnings)


def test_doctor_groups_broken_links_by_file(test_repo):
    """One warning per file, however many links in it are broken."""
    (test_repo.root / "notes" / "note.md").write_text("[a](gone-a.md)\n\n[b](gone-b.md)\n")

    report = doctor(test_repo)

    warnings = [w for w in report.warnings if "notes/note.md" in w]
    assert len(warnings) == 1
    assert "gone-a.md" in warnings[0]
    assert "gone-b.md" in warnings[0]


def test_doctor_is_idempotent(test_repo):
    """doctor() reports nothing when everything is already in place."""
    doctor(test_repo)

    report = doctor(test_repo)

    assert report.actions == []
    assert report.warnings == []


def test_doctor_commits_what_it_creates(test_repo):
    """A recreated file is committed, alone: doctor leaves nothing staged for someone else's commit."""
    gitignore = test_repo.root / ".gitignore"
    gitignore.unlink()
    git(test_repo.root, "rm", "-q", "--cached", ".gitignore")
    git(test_repo.root, "commit", "-qm", "Lose .gitignore")

    doctor(test_repo)

    assert git(test_repo.root, "show", "HEAD:.gitignore") == gitignore.read_text()
    assert git(test_repo.root, "diff", "--name-only", "HEAD~1", "HEAD").split() == [".gitignore"]
    assert git(test_repo.root, "status", "--porcelain") == ""


def test_doctor_check_reports_missing_scaffolding_without_writing(test_repo):
    gitignore = test_repo.root / ".gitignore"
    gitignore.unlink()
    head = git(test_repo.root, "rev-parse", "HEAD")

    report = doctor(test_repo, check=True)

    assert any(".gitignore" in action for action in report.actions)
    assert not gitignore.exists()
    assert git(test_repo.root, "rev-parse", "HEAD") == head


def _doctor_log(test_repo, caplog, **kwargs) -> list[str]:
    with caplog.at_level(logging.INFO, logger="commonplace"):
        doctor(test_repo, **kwargs)
    return [r.getMessage() for r in caplog.records]


def _first(lines: list[str], text: str) -> int:
    return next(i for i, line in enumerate(lines) if text in line)


def test_doctor_logs_each_operation_header_before_its_results(test_repo, caplog):
    (test_repo.root / ".gitignore").unlink()
    (test_repo.root / "notes" / "note.md").write_text("See [the other one](gone.md).\n")

    lines = _doctor_log(test_repo, caplog)

    scaffold, links = _first(lines, "── scaffold"), _first(lines, "── links")
    assert scaffold < _first(lines, ".gitignore") < links < _first(lines, "gone.md")


def test_doctor_skipped_operation_logs_only_its_skip_line(test_repo, caplog):
    (test_repo.root / "notes" / "note.md").write_text("See [the other one](gone.md).\n")

    lines = _doctor_log(test_repo, caplog, links=False)

    assert [line for line in lines if "links" in line or "gone.md" in line] == [
        next(line for line in lines if "skipped" in line)
    ]


def test_doctor_numbers_each_operation_heading_in_run_order(test_repo, caplog):
    headings = [line for line in _doctor_log(test_repo, caplog, links=False) if line.startswith("── ")]

    assert headings
    assert all(f"({n}/{len(headings)})" in heading for n, heading in enumerate(headings, 1))


def test_doctor_ends_with_a_summary_line(test_repo, caplog):
    lines = _doctor_log(test_repo, caplog)

    assert lines[-1].startswith("doctor:")


def test_doctor_cli_no_links_skips_the_link_check(test_app, test_repo, caplog):
    (test_repo.root / "notes" / "note.md").write_text("See [the other one](gone.md).\n")

    with caplog.at_level(logging.INFO, logger="commonplace"):
        assert test_app(["doctor", "--no-links"]) == 0

    assert not [r for r in caplog.records if "gone.md" in r.getMessage()]
