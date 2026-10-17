"""Draw a dream's day residue from a commonplace and print it as JSON."""

import argparse
import json
import random
import re
import subprocess
from pathlib import Path

PATHSPEC = ["chats", "journal", "notes", "memory", ":!chats/claude-tasks"]
RECENT, TOTAL, MEMORY_CAP, LIMIT = 6, 12, 2, 2000
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
HEADING = re.compile(r"^## ", re.MULTILINE)


def git_paths(root: Path, *args: str) -> list[str]:
    """Existing markdown paths a git command names, deduplicated and sorted."""
    out = subprocess.run(["git", "-C", str(root), *args, "-z", "--", *PATHSPEC], check=True, capture_output=True)
    paths = {p.strip("\n") for p in out.stdout.decode().split("\0")}
    return sorted(p for p in paths if p.endswith(".md") and (root / p).is_file())


def section(text: str, rng: random.Random) -> tuple[str | None, str]:
    """One random `## ` section, or the whole file if it has none, without frontmatter and cut to LIMIT."""
    text = FRONTMATTER.sub("", text)
    starts = [m.start() for m in HEADING.finditer(text)] + [len(text)]
    if len(starts) == 1:
        return None, text[:LIMIT]
    i = rng.randrange(len(starts) - 1)
    body = text[starts[i] : starts[i + 1]]
    return body.splitlines()[0][3:].strip(), body[:LIMIT]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--seed", type=int, help="reproduce a draw")
    args = parser.parse_args()
    rng = random.Random(args.seed)

    recent: list[str] = []
    pool = git_paths(args.root, "log", "--since=7.days", "--name-only", "--format=")
    rng.shuffle(pool)
    for path in pool:
        memory = sum(p.startswith("memory/") for p in recent)
        if len(recent) < RECENT and not (path.startswith("memory/") and memory == MEMORY_CAP):
            recent.append(path)
    deep_pool = [p for p in git_paths(args.root, "ls-files") if p not in recent]
    deep = rng.sample(deep_pool, min(len(deep_pool), TOTAL - len(recent)))

    fragments = []
    for draw, paths in (("recent", recent), ("deep", deep)):
        for path in paths:
            heading, text = section((args.root / path).read_text(errors="replace"), rng)
            fragments.append({"path": path, "heading": heading, "text": text, "draw": draw})
    print(json.dumps(fragments, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
