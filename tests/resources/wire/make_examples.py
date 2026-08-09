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


def main() -> None:
    for version, (header, entries) in ARCHIVES.items():
        lines = [] if header is None else [json.dumps(header)]
        lines += [json.dumps(entry, ensure_ascii=False) for entry in entries]
        body = "".join(line + "\n" for line in lines)
        path = OUT / f"claude-v{version}.jsonl.gz"
        path.write_bytes(gzip.compress(body.encode("utf-8"), mtime=0))
        print(f"wrote {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
