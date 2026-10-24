"""Pool a dream's images blind, split the telling from its Unused list, and write the record nobody reads."""

import argparse
import json
import random
import re
import sys
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


def split(scratch: Path) -> None:
    """Cut scenes.txt into telling.txt and unused.txt, so later phases read the telling alone."""
    text = (scratch / "scenes.txt").read_text()
    if "\nUnused:" not in text:
        sys.exit("scenes.txt has no Unused: section")
    telling, unused = text.split("\nUnused:", 1)
    (scratch / "telling.txt").write_text(telling.rstrip() + "\n")
    (scratch / "unused.txt").write_text("".join(f"{s}\n" for s in map(str.strip, unused.splitlines()) if s))


def field(text: str, name: str) -> str:
    """The value of a `Name: value` line."""
    return next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith(f"{name}:"))


def residue(scratch: Path) -> list[str]:
    """Each fragment's residue line, marking its images used, unused or leaked, then any stray Unused lines."""
    fragments = json.loads((scratch / "fragments.json").read_text())
    images = json.loads((scratch / "images.json").read_text())
    unused = set((scratch / "unused.txt").read_text().splitlines())
    lines = []
    for n, fragment in enumerate(fragments, 1):
        marks = [
            f"{i['image']} ({'leaked' if i['leaked'] else 'unused' if i['image'] in unused else 'used'})"
            for i in images
            if i["fragment"] == n
        ]
        heading = f", {fragment['heading']}" if fragment["heading"] else ""
        lines.append(f"- [[/{fragment['path'].removesuffix('.md')}]]{heading}: {'; '.join(marks)}")
    if stray := sorted(unused - {i["image"] for i in images if not i["leaked"]}):
        lines += ["", "Unused but not in the pool:", *(f"- {s}" for s in stray)]
    return lines


def overlap(scratch: Path) -> str:
    """How many of the interpretation's citations were residue, and how many fragments it found."""
    paths = {f"{f['path'].removesuffix('.md')}" for f in json.loads((scratch / "fragments.json").read_text())}
    cited = set(re.findall(r"\[\[/([^\]|#]+)", (scratch / "interpretation.txt").read_text()))
    found = cited & paths
    return f"{len(found)} of {len(cited)} cited sources were residue; {len(found)} of {len(paths)} fragments found."


def record(scratch: Path, root: Path, agent: str, date: str, by: str, at: str) -> None:
    """Write the dream's record, unread by anyone, and print only its path."""
    telling = (scratch / "telling.txt").read_text()
    title = field((scratch / "dream.txt").read_text(), "Title")
    yyyy, mm, _ = date.split("-")
    journal = f"/agent-journal/{agent}/{yyyy}/{mm}/{date}"
    path = Path(".commonplace/skills/dream") / agent / yyyy / mm / f"{date}-{field(telling, 'Summary')}.md"
    fragments = json.loads((scratch / "fragments.json").read_text())
    accents = (scratch / "accents.txt").read_text().strip() if (scratch / "accents.txt").exists() else "Nothing."
    text = "\n".join(
        [
            "---",
            f"title: {title}",
            "residue:",
            *(f"  - /{f['path']}" for f in fragments),
            f"journal: {journal}.md",
            f"generated: {{by: {by}, at: {at}}}",
            "---",
            "",
            f"# {title}",
            "",
            f"The dream, its waking and its interpretation: [[{journal}]].",
            "",
            "## Residue",
            *residue(scratch),
            "",
            "## Unpolished",
            telling.split("\n\n", 1)[1].strip(),
            "",
            "## Accents",
            accents,
            "",
            "## Interpretation",
            overlap(scratch),
            "",
        ]
    )
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text)
    print(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["pool", "split", "record"])
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--seed", type=int, help="reproduce a shuffle")
    parser.add_argument("--root", type=Path, help="record: the repository to write into")
    parser.add_argument("--agent", help="record: the dreaming agent, e.g. claude-code")
    parser.add_argument("--date", help="record: today, YYYY-MM-DD")
    parser.add_argument("--by", help="record: generated.by, e.g. dream/0.26.0")
    parser.add_argument("--at", help="record: generated.at, e.g. 2026-10-24T12:00:00Z")
    args = parser.parse_args()
    if args.step == "pool":
        pool(args.scratch, args.seed)
    elif args.step == "split":
        split(args.scratch)
    else:
        record(args.scratch, args.root, args.agent, args.date, args.by, args.at)


if __name__ == "__main__":
    main()
