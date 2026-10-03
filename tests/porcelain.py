import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    """Run git in `root` as someone other than the bot, through the porcelain; returns stdout."""
    identity = ["-c", "user.name=Other", "-c", "user.email=other@example.com", "-c", "init.defaultBranch=main"]
    return subprocess.run(["git", "-C", str(root), *identity, *args], capture_output=True, text=True, check=True).stdout
