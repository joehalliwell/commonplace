"""Tests for the script the tag-on-merge workflow uses to pick the next version from a PR's semver label."""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "next-version.sh"


def next_version(latest: str, labels: str) -> subprocess.CompletedProcess[str]:
    # Not check=True: the failures are what half the tests are about.
    return subprocess.run(["bash", str(SCRIPT), latest, labels], capture_output=True, text=True, check=False)


@pytest.mark.parametrize(
    ("latest", "bump", "expected"),
    [
        ("1.0.0", "patch", "1.0.1"),
        ("1.0.9", "patch", "1.0.10"),
        ("1.4.2", "minor", "1.5.0"),
        ("1.4.2", "major", "2.0.0"),
    ],
)
def test_next_version_bumps_by_the_prs_label(latest, bump, expected):
    result = next_version(latest, f'["documentation", "semver:{bump}"]')

    assert (result.returncode, result.stdout) == (0, f"{expected}\n")


@pytest.mark.parametrize("labels", ['["documentation"]', '["semver:minor", "semver:patch"]', '["semver:huge"]'])
def test_next_version_refuses_without_exactly_one_known_semver_label(labels):
    """The label check should stop such a PR merging; this is the backstop."""
    result = next_version("1.0.0", labels)

    assert result.returncode != 0
    assert "semver" in result.stderr


def test_next_version_refuses_a_latest_tag_that_isnt_a_version():
    result = next_version("not-a-version", '["semver:patch"]')

    assert result.returncode != 0
