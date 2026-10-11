"""Regenerate the example wire archives in this directory: `just wire-examples`.

One archive per wire version, each holding the same conversation, so tests can
assert that every version we have ever written still imports to the same thing.
The `any_wire_version` fixture is parametrised over the full version range, so
a bump without a matching example here fails the suite.

The memory wire has its own examples from v3, when it first appeared. Nothing
yet fails if a bump forgets one, so add it alongside the chat example.

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
    # The model in use now; a safeguard fallback names the ones before it.
    "model": "claude-sonnet-4-6",
    "settings": {
        "safeguard_fallback": {
            "turn_uuid": "m2",
            "hops": [{"from_model": {"model": "claude-fable-5"}, "to_model": {"model": "claude-opus-4-8"}}],
        }
    },
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
    "updated_at": "2026-09-30T10:00:00.123456Z",
    "memory_id": "mem_example",
    "display_name": "Example",
    "category_id": "topics",
    "display_path_segments": ["Topics", "Example"],
    "description": "A synthetic memory",
}
# Shaped like the real thing as first fetched on 2026-10-02: these four keys, no trailing newline.
MEMORY_CONTENT = (
    "---\nname: example\ndescription: A synthetic memory\nsources: [backfill]\naliases: []\n---\n"
    "- [stated] Prefers tea. See [[other]]."
)
MEMORY_READ = MEMORY_LISTED | {
    "memory_id": "",
    "content": MEMORY_CONTENT,
    "version": "a1b2c3d4e5f6",
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


# Shaped like the real thing as first fetched on 2026-10-04: newest update first, two trailing ints we don't
# understand, and an opaque base64 token after the items.
GEMINI_SAVED_INFO = [
    [
        [
            "0006376600000000000000000000000000000000000000a1",
            "Prefers tea to coffee.",
            [1767225600, 0],
            None,
            [1767398400, 500000000],
            None,
            None,
            None,
            None,
            1,
            5,
        ],
        [
            "0006376600000000000000000000000000000000000000b2",
            "Writes in British English.",
            [1735689600, 0],
            None,
            [1767312000, 0],
            None,
            None,
            None,
            None,
            2,
            1,
        ],
    ],
    "c3ludGhldGljIHRva2Vu",
]
GEMINI_SAVED_INFO_TEXT = ")]}'\n\n0\n" + json.dumps(
    [["wrb.fr", "ZKcapf", json.dumps(GEMINI_SAVED_INFO), None, None, None, "generic"]]
)

GEMINI_MEMORY_ARCHIVES: dict[int, tuple[dict | None, list[dict]]] = {
    3: (
        {
            "wire": "gemini-memory",
            "version": 3,
            "fetched_at": "2026-10-04T12:00:00+00:00",
            "fetched_by": "commonplace/0.0.5",
        },
        [{"rpc": "ZKcapf", "payload": [], "response": GEMINI_SAVED_INFO_TEXT}],
    ),
}

# Synthetic, shaped like the about-you summary as first fetched on 2026-10-03: one event per
# section, then `done` restating them all. The last section is only follow-up prompts.
CHATGPT_SECTIONS = [
    {"id": "overview", "title": "Overview", "description": "Prefers tea, and asks for sources."},
    {
        "id": "dive-deeper",
        "title": "Dive deeper",
        "description": "",
        "followUps": [{"preview": "Tea?", "prompt": "Tell me about tea.", "action": "start_chat"}],
    },
]
CHATGPT_HEAD = {"generatedAtIso": "2026-10-03T22:27:53.035594+00:00", "sourceChecksum": "5c24" * 16}
CHATGPT_EVENTS = [
    ("started", CHATGPT_HEAD),
    (
        "section_types",
        {
            "generatedAtIso": CHATGPT_HEAD["generatedAtIso"],
            "sections": [{"id": s["id"], "title": s["title"]} for s in CHATGPT_SECTIONS],
        },
    ),
    *(("section", {"section": s}) for s in CHATGPT_SECTIONS),
    ("done", {"emptyStateMessage": "Chat more to see a summary.", **CHATGPT_HEAD, "sections": CHATGPT_SECTIONS}),
]
CHATGPT_STREAM = (
    "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in CHATGPT_EVENTS) + "data: [DONE]\n\n"
)

CHATGPT_MEMORY_ARCHIVES: dict[int, tuple[dict | None, list[dict]]] = {
    3: (
        {
            "wire": "chatgpt-memory",
            "version": 3,
            "fetched_at": "2026-10-03T23:00:00+00:00",
            "fetched_by": "commonplace/0.0.5",
        },
        [
            {
                "endpoint": "memories",
                "response": json.dumps({"memories": [], "memory_max_tokens": 5000000, "memory_num_tokens": 0}),
            },
            {"endpoint": "summary", "response": CHATGPT_STREAM},
        ],
    ),
}


# Synthetic, shaped like one scheduled run as first fetched on 2026-10-11. Numbers arrive as strings,
# events newest first, thinking only as a signature, and the prompt from the client with no payload timestamp.
TASK_RUN = {
    "id": "cse_01Example",
    "trigger_id": "trig_01Example",
    "title": "⚡ Morning digest",
    "created_at": "2026-10-11T05:10:31.312825Z",
    "updated_at": "2026-10-11T09:36:49.480652Z",
    "last_event_at": "2026-10-11T05:13:12.369251Z",
    "config": {"model": "claude-opus-5-5", "origin": "scheduled_trigger", "permission_mode": "auto"},
    "environment_kind": "anthropic_cloud",
    "status": "active",
    "tags": ["cowork-scheduled"],
    "user_message_count": "0",
}


def _task_event(seq: int, at: str, payload: dict, source: str = "worker") -> dict:
    stamp = {"timestamp": at} if source == "worker" else {}
    return {
        "event_id": f"ev-{seq}",
        "event_type": payload["type"],
        "sequence_num": str(seq),
        "source": source,
        "created_at": at,
        "payload": {"session_id": "s-example", "uuid": f"u-{seq}", **stamp, **payload},
    }


def _assistant(*content: dict) -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-5-5", "content": list(content)}}


TASK_EVENTS = [
    _task_event(
        1, "2026-10-11T05:10:40Z", {"type": "user", "message": {"role": "user", "content": "Find news."}}, "client"
    ),
    _task_event(2, "2026-10-11T05:10:41Z", {"type": "system", "subtype": "status"}),
    _task_event(3, "2026-10-11T05:10:45Z", _assistant({"type": "thinking", "thinking": "", "signature": "c2ln"})),
    _task_event(
        4,
        "2026-10-11T05:10:46Z",
        _assistant({"type": "tool_use", "id": "toolu_1", "name": "WebSearch", "input": {"query": "news"}}),
    ),
    _task_event(
        5,
        "2026-10-11T05:11:54Z",
        {
            "type": "user",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "x"}]},
        },
    ),
    _task_event(6, "2026-10-11T05:13:12Z", _assistant({"type": "text", "text": "[AI] Nothing new today"})),
    _task_event(
        7, "2026-10-11T05:13:13Z", {"type": "result", "subtype": "success", "result": "[AI] Nothing new today"}
    ),
    # A reply in the run's chat makes it a conversation: one more turn, one more result.
    _task_event(
        8, "2026-10-11T07:00:00Z", {"type": "user", "message": {"role": "user", "content": "Why not?"}}, "client"
    ),
    _task_event(9, "2026-10-11T07:00:05Z", _assistant({"type": "text", "text": "A quiet night."})),
    _task_event(10, "2026-10-11T07:00:06Z", {"type": "result", "subtype": "success", "result": "A quiet night."}),
]

#: The scheduled-run wire first appeared at v3, so it has no earlier examples.
TASK_ARCHIVES: dict[int, tuple[dict | None, list[dict]]] = {
    3: (
        {
            "wire": "claude-tasks",
            "version": 3,
            "fetched_at": "2026-10-11T12:00:00+00:00",
            "fetched_by": "commonplace/0.0.5",
        },
        [
            {"endpoint": "sessions", "response": json.dumps({"data": [TASK_RUN], "resume_token": "cmVzdW1l"})},
            {
                "endpoint": "events",
                "sid": "cse_01Example",
                "response": json.dumps({"data": TASK_EVENTS[::-1], "resume_cursor": "cmVzdW1l"}),
            },
        ],
    ),
}


def main() -> None:
    for source, archives in (
        ("claude", ARCHIVES),
        ("claude-memory", MEMORY_ARCHIVES),
        ("claude-tasks", TASK_ARCHIVES),
        ("chatgpt-memory", CHATGPT_MEMORY_ARCHIVES),
        ("gemini-memory", GEMINI_MEMORY_ARCHIVES),
    ):
        for version, (header, entries) in archives.items():
            lines = [] if header is None else [json.dumps(header)]
            lines += [json.dumps(entry, ensure_ascii=False) for entry in entries]
            body = "".join(line + "\n" for line in lines)
            path = OUT / f"{source}-v{version}.jsonl.gz"
            path.write_bytes(gzip.compress(body.encode("utf-8"), mtime=0))
            print(f"wrote {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
