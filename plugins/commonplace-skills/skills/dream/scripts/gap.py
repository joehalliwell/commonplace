"""Pool a dream's images blind, then check the scenes' Unused list and print the record's residue lines."""

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


def check(scratch: Path) -> None:
    """Print each fragment's residue line, marking its images used, unused or leaked, then any stray Unused lines."""
    fragments = json.loads((scratch / "fragments.json").read_text())
    images = json.loads((scratch / "images.json").read_text())
    lines = [s.strip() for s in (scratch / "scenes.txt").read_text().splitlines()]
    unused = set(lines[lines.index("Unused:") + 1 :]) - {""} if "Unused:" in lines else set()
    for n, fragment in enumerate(fragments, 1):
        marks = [
            f"{i['image']} ({'leaked' if i['leaked'] else 'unused' if i['image'] in unused else 'used'})"
            for i in images
            if i["fragment"] == n
        ]
        heading = f", {fragment['heading']}" if fragment["heading"] else ""
        print(f"- [[/{fragment['path'].removesuffix('.md')}]]{heading}: {'; '.join(marks)}")
    stray = sorted(unused - {i["image"] for i in images if not i["leaked"]})
    if stray:
        print("Unused but not in the pool:")
        print("\n".join(f"- {s}" for s in stray))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["pool", "check"])
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--seed", type=int, help="reproduce a shuffle")
    args = parser.parse_args()
    if args.step == "pool":
        pool(args.scratch, args.seed)
    else:
        check(args.scratch)


if __name__ == "__main__":
    main()
