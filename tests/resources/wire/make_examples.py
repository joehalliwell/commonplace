"""Regenerate the example wire archives in this directory: `just wire-examples`.

One archive per wire version, each holding the same conversation, so tests can
assert that every version we have ever written still imports to the same thing.
The `any_wire_version` fixture is parametrised over the full version range, so
a bump without a matching example here fails the suite.

Adding a version: add its header and entries below, then rerun. Output is
deterministic — gzip's mtime is pinned — so an unchanged version stays
byte-identical and only the new file shows up in the diff.
"""

import gzip
import json
from pathlib import Path

OUT = Path(__file__).parent

SUMMARY = {"uuid": "c-example", "name": "Example", "updated_at": "2026-07-15T00:00:01Z"}
THREAD = {
    "uuid": "c-example",
    "name": "Example",
    "created_at": "2026-07-15T00:00:00Z",
    "updated_at": "2026-07-15T00:00:01Z",
    "chat_messages": [
        {"uuid": "m1", "sender": "human", "text": "hello", "created_at": "2026-07-15T00:00:00Z"},
        {"uuid": "m2", "sender": "assistant", "text": "hi back", "created_at": "2026-07-15T00:00:01Z"},
    ],
}

# v1 stored `response` already parsed; v2 onwards store the verbatim body text.
LIST_TEXT = json.dumps([SUMMARY])
THREAD_TEXT = json.dumps(THREAD)

#: version -> (header or None for the pre-versioning format, entries)
ARCHIVES: dict[int, tuple[dict | None, list[dict]]] = {
    1: (
        None,
        [
            {"endpoint": "conversations", "response": [SUMMARY]},
            {"endpoint": "conversation", "cid": "c-example", "response": THREAD},
        ],
    ),
    2: (
        {"wire": "claude", "version": 2},
        [
            {"endpoint": "conversations", "response": LIST_TEXT},
            {"endpoint": "conversation", "cid": "c-example", "response": THREAD_TEXT},
        ],
    ),
    3: (
        {
            "wire": "claude",
            "version": 3,
            "fetched_at": "2026-08-09T12:00:00+00:00",
            "fetched_by": "commonplace/0.0.5",
        },
        [
            {"endpoint": "conversations", "request_id": "req_011example1", "response": LIST_TEXT},
            {
                "endpoint": "conversation",
                "cid": "c-example",
                "request_id": "req_011example2",
                "response": THREAD_TEXT,
            },
        ],
    ),
}


# Synthetic: real memory is personal and this directory is public.
MEMORY_LISTED = {
    "path": "/topics/example.md",
    "size_bytes": 96,
    "updated_at": "2026-09-30T10:00:00Z",
    "memory_id": "mem_example",
    "display_name": "Example",
    "category_id": "topics",
    "display_path_segments": ["Topics", "Example"],
    "description": "A synthetic memory",
}
MEMORY_CONTENT = "---\nname: Example\ndescription: A synthetic memory\n---\n\nPrefers tea. See [[other]].\n"
MEMORY_READ = MEMORY_LISTED | {
    "memory_id": "",
    "content": MEMORY_CONTENT,
    "version": "a1b2c3",
    "path_segments": ["topics", "example.md"],
    "parsed": {"name": "Example", "description": "A synthetic memory", "metadata": {}, "body": ""},
}
MEMORY_CATEGORIES = [{"id": "topics", "display_name": "Topics", "sort_order": 0, "behavior_hint": None}]

#: The memory wire first appeared at v3, so it has no earlier examples.
MEMORY_ARCHIVES: dict[int, tuple[dict | None, list[dict]]] = {
    3: (
        {
            "wire": "claude-memory",
            "version": 3,
            "fetched_at": "2026-10-02T12:00:00+00:00",
            "fetched_by": "commonplace/0.0.5",
        },
        [
            {
                "endpoint": "list",
                "request_id": "req_011example3",
                "response": json.dumps({"data": [MEMORY_LISTED], "categories": MEMORY_CATEGORIES}),
            },
            {
                "endpoint": "read",
                "path": "/topics/example.md",
                "request_id": "req_011example4",
                "response": json.dumps(MEMORY_READ),
            },
        ],
    ),
}


def main() -> None:
    for source, archives in (("claude", ARCHIVES), ("claude-memory", MEMORY_ARCHIVES)):
        for version, (header, entries) in archives.items():
            lines = [] if header is None else [json.dumps(header)]
            lines += [json.dumps(entry, ensure_ascii=False) for entry in entries]
            body = "".join(line + "\n" for line in lines)
            path = OUT / f"{source}-v{version}.jsonl.gz"
            path.write_bytes(gzip.compress(body.encode("utf-8"), mtime=0))
            print(f"wrote {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
