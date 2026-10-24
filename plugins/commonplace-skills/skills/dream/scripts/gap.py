"""Pool a dream's images blind, then write its telling and the trace nobody reads."""

import argparse
import json
import random
import re
from pathlib import Path

NAME = re.compile(r"\b[A-Z][\w'’-]*")
SENTENCE_START = ("", ".", "!", "?", '"', "“", ":")


def names(image: str) -> set[str]:
    """Capitalised words in an image that don't open a sentence."""
    return {
        m.group()
        for m in NAME.finditer(image)
        if m.group() != "I" and image[: m.start()].rstrip()[-1:] not in SENTENCE_START
    }


def pool(scratch: Path, seed: int | None) -> None:
    """Pool every image, dropping any that reuses a name from its passage, and shuffle the rest into pool.txt."""
    images = []
    for n in range(1, len(json.loads((scratch / "fragments.json").read_text())) + 1):
        passage = (scratch / "passages" / f"{n}.txt").read_text()
        path = scratch / "images" / f"{n}.txt"
        for image in path.read_text().splitlines() if path.exists() else []:
            if image := image.strip():
                leaked = any(re.search(rf"\b{re.escape(w)}\b", passage) for w in names(image))
                images.append({"image": image, "fragment": n, "leaked": leaked})
    kept = [i["image"] for i in images if not i["leaked"]]
    random.Random(seed).shuffle(kept)
    (scratch / "images.json").write_text(json.dumps(images, indent=1, ensure_ascii=False))
    (scratch / "pool.txt").write_text("".join(f"{i}\n" for i in kept))
    print(f"{len(kept)} images in the pool, {len(images) - len(kept)} leaked")


def title(scratch: Path) -> str:
    """The dream's title, from its `Title:` line."""
    text = (scratch / "dream.txt").read_text()
    return next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("Title:"))


def slug(text: str) -> str:
    """A kebab-case slug for a file name."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def residue(scratch: Path) -> list[str]:
    """Each fragment's residue line: its path and heading, and the images it became, marking the leaked."""
    fragments = json.loads((scratch / "fragments.json").read_text())
    images = json.loads((scratch / "images.json").read_text())
    lines = []
    for n, fragment in enumerate(fragments, 1):
        marks = [f"{i['image']}{' (leaked)' if i['leaked'] else ''}" for i in images if i["fragment"] == n]
        heading = f", {fragment['heading']}" if fragment["heading"] else ""
        lines.append(f"- [[/{fragment['path'].removesuffix('.md')}]]{heading}: {'; '.join(marks)}")
    return lines


def overlap(scratch: Path) -> str:
    """How many of the interpretation's citations were residue, and how many fragments it found."""
    paths = {f"{f['path'].removesuffix('.md')}" for f in json.loads((scratch / "fragments.json").read_text())}
    cited = set(re.findall(r"\[\[/([^\]|#]+)", (scratch / "interpretation.txt").read_text()))
    found = cited & paths
    return f"{len(found)} of {len(cited)} cited sources were residue; {len(found)} of {len(paths)} fragments found."


def trace(scratch: Path, root: Path, agent: str, date: str, by: str, at: str) -> None:
    """Write the telling and, beside it, the trace nobody reads, and print only the telling's path."""
    name = title(scratch)
    yyyy, mm, _ = date.split("-")
    stem = Path(".commonplace/skills/dream") / agent / yyyy / mm / f"{date}-{slug(name)}"
    path, n = Path(f"{stem}.md"), 1
    while (root / path).exists():  # a second dream with the same title that day
        n += 1
        path = Path(f"{stem}-{n}.md")
    fragments = json.loads((scratch / "fragments.json").read_text())
    telling = (scratch / "dream.txt").read_text().split("\n\n", 1)[1].strip()
    front = [f"journal: /agent-journal/{agent}/{yyyy}/{mm}/{date}.md", f"generated: {{by: {by}, at: {at}}}"]
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text("\n".join(["---", f"title: {name}", *front, "---", "", f"# {name}", "", telling, ""]))
    (root / path).with_suffix(".trace.md").write_text(
        "\n".join(
            [
                "---",
                "residue:",
                *(f"  - /{f['path']}" for f in fragments),
                *front,
                "---",
                "",
                f"# Trace: {name}",
                "",
                "## Residue",
                *residue(scratch),
                "",
                "## Interpretation",
                overlap(scratch),
                "",
            ]
        )
    )
    print(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["pool", "trace"])
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--seed", type=int, help="reproduce a shuffle")
    parser.add_argument("--root", type=Path, help="trace: the repository to write into")
    parser.add_argument("--agent", help="trace: the agent running the skill, e.g. claude-code")
    parser.add_argument("--date", help="trace: today, YYYY-MM-DD")
    parser.add_argument("--by", help="trace: generated.by, e.g. dream/0.26.0")
    parser.add_argument("--at", help="trace: generated.at, e.g. 2026-10-24T12:00:00Z")
    args = parser.parse_args()
    if args.step == "pool":
        pool(args.scratch, args.seed)
    else:
        trace(args.scratch, args.root, args.agent, args.date, args.by, args.at)


if __name__ == "__main__":
    main()
