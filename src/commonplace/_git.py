"""Low-level git CLI plumbing: lock retries, NUL-delimited queries, scoped staging and hook-aware commits.

Every git operation goes through the git CLI via `run_git`, never a library: re-implementing the porcelain cost
a silent revert (#102). Commits stage and commit only the paths named and run the user's hooks, re-staging once
if a hook reformats them.
"""

import os
import subprocess
import time
from functools import lru_cache
from itertools import batched
from pathlib import Path

from commonplace._logging import logger

_BOT_USERNAME = "Commonplace Bot"
_BOT_EMAIL = "commonplace@joehalliwell.com"

# Seconds to wait between attempts while another git process holds a lock.
_LOCK_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)

# Imports touch thousands of paths, more than argv holds.
_PATHSPEC_STDIN = ("--pathspec-from-file=-", "--pathspec-file-nul")


class GitError(ValueError):
    """A git command that failed, with what it printed."""


def run_git(root: Path, *args: str, input: str | None = None, as_user: bool = False) -> str:
    """Run git in `root` as the bot, or as the user's own git identity, waiting out another process's lock."""
    env = os.environ | {"LC_ALL": "C", "GIT_LITERAL_PATHSPECS": "1"}
    if not as_user:
        env |= {
            "GIT_AUTHOR_NAME": _BOT_USERNAME,
            "GIT_AUTHOR_EMAIL": _BOT_EMAIL,
            "GIT_COMMITTER_NAME": _BOT_USERNAME,
            "GIT_COMMITTER_EMAIL": _BOT_EMAIL,
        }
    cmd = ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args]
    delays = iter(_LOCK_RETRY_DELAYS)
    while True:
        done = subprocess.run(cmd, input=input, capture_output=True, text=True, encoding="utf-8", env=env, check=False)
        if done.returncode == 0:
            return done.stdout
        delay = next(delays, None)
        if delay is None or ".lock': File exists" not in done.stderr:
            raise GitError(f"git {args[0]} failed:\n{done.stdout}{done.stderr}".strip())
        logger.debug(f"Waiting {delay}s for a git lock: {done.stderr.strip()}")
        time.sleep(delay)


def z(root: Path, command: str, *args: str) -> list[str]:
    """The fields `git <command> -z <args>` prints, separated by NULs."""
    return [field for field in run_git(root, command, "-z", *args).split("\0") if field]


def _changed(root: Path, paths: set[str], *diff_args: str) -> set[str]:
    """Those of `paths` that `git diff <diff_args>` reports."""
    return set(z(root, "diff", "--name-only", "--no-renames", *diff_args)) & paths


def _stage(root: Path, paths: set[str]) -> None:
    """Stage exactly `paths`, deletions included."""
    present = {p for p in paths if (root / p).exists()}
    if present:
        run_git(root, "add", *_PATHSPEC_STDIN, input="\0".join(present))
    if paths - present:
        run_git(root, "rm", "--cached", "-q", "--ignore-unmatch", *_PATHSPEC_STDIN, input="\0".join(paths - present))


def commit(root: Path, paths: set[str], message: str, as_user: bool = False) -> bool:
    """Commit exactly `paths`, re-staging once if a hook reformats them; False if there was nothing to commit."""
    _stage(root, paths)
    try:
        return _commit_staged(root, paths, message, as_user)
    except GitError:
        if not (reformatted := _changed(root, paths)):
            raise
        logger.info(f"A hook rewrote {len(reformatted)} file(s); committing its version")
        _stage(root, reformatted)
        # The hook's version may be exactly what HEAD already has, as on a re-import.
        return _commit_staged(root, paths, message, as_user)


def _commit_staged(root: Path, paths: set[str], message: str, as_user: bool) -> bool:
    """Commit those of `paths` staged unlike HEAD; False if none are."""
    if not (changed := _changed(root, paths, "--cached")):
        return False
    run_git(root, "commit", "-q", "-m", message, *_PATHSPEC_STDIN, input="\0".join(changed), as_user=as_user)
    return True


@lru_cache(maxsize=4)
def last_changed(root: Path, head: str, pathspec: str, field: str) -> dict[str, str]:
    """Each path under `pathspec` in `head`'s history, newest first, with `field` of the last commit to change it.

    Keyed by `head`, since a commit moves it and a map built before would go on reporting the superseded commit.
    """
    out = run_git(root, "log", f"--format=%x00>{field}", "--name-only", "-z", "--no-renames", head, "--", pathspec)
    # Each commit is an empty token, its field after a `>` so it is never empty, then the paths it changed.
    last: dict[str, str] = {}
    tokens = iter(out.split("\0"))
    value = ""
    for token in tokens:
        if not token:
            value = next(tokens, "")[1:]
        else:
            last.setdefault(token.lstrip("\n"), value)
    return last


def hash_objects(root: Path, paths: list[str]) -> list[str]:
    """Git's id for the content of each file at `paths` as the working tree has it, in order."""
    # As arguments, not --stdin-paths, which splits on newlines and C-unquotes a path starting with a quote.
    return [id_ for batch in batched(paths, 256) for id_ in run_git(root, "hash-object", "--", *batch).split()]


@lru_cache(maxsize=2)
def content_ids(root: Path, head: str) -> dict[str, str]:
    """Each file in `head`'s tree, with git's id for its content; keyed by `head`, as `last_changed` is."""
    # -z gives `<mode> <type> <id>\t<path>` for each file.
    return {path: meta.split()[2] for meta, path in (e.split("\t", 1) for e in z(root, "ls-tree", "-r", head))}
