"""Redact a raw Gemini `batchexecute` response, preserving structure.

Used to prepare test fixtures from live wire captures. Replaces prose
strings (message text, thoughts, gem prompts, chat titles) with
placeholders while keeping IDs, timestamps, cursors, and positional
layout intact — so tests exercise the full parse chain.

Usage:
    python scripts/redact_gemini_fixture.py <raw> <mode> <out>
    mode is `list_chats` or `read_chat`.
"""

import json
import sys
from pathlib import Path

PREAMBLE = ")]}'\n"


def parse_response(text: str) -> list[str]:
    """Return the list of chunk JSON strings.

    Skips size prefixes (Google's counts are UTF-16 code units, not Python
    chars) and instead uses JSONDecoder.raw_decode to find each chunk's end.
    """
    assert text.startswith(PREAMBLE)
    rest = text[len(PREAMBLE) :]
    decoder = json.JSONDecoder()
    chunks = []
    i = 0
    while i < len(rest):
        # Skip whitespace + numeric size prefixes until we hit '['
        while i < len(rest) and rest[i] != "[":
            i += 1
        if i >= len(rest):
            break
        obj, offset = decoder.raw_decode(rest, i)
        chunks.append(rest[i : i + offset - i])
        i += offset - i
    return chunks


def rebuild_response(chunks: list[str]) -> str:
    out = [PREAMBLE]
    for chunk in chunks:
        out.append(f"\n{len(chunk)}\n{chunk}")
    return "".join(out)


def _walk_replace_prose(obj):
    """Recursively replace any string that looks like natural language.

    Heuristic: contains a space (real prose does; IDs, tokens, and codes
    don't). Length threshold is deliberately low — Gemini emits short
    thought-section labels and short titles that can carry sensitive
    context, so we err on the side of over-redacting anything with
    whitespace. Cursors, rcids, colours, and language/country codes have
    no spaces and pass through.
    """
    if isinstance(obj, list):
        return [_walk_replace_prose(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _walk_replace_prose(v) for k, v in obj.items()}
    if isinstance(obj, str) and " " in obj:
        return "REDACTED_PROSE"
    return obj


def redact_read_chat_body(body: list) -> None:
    """Walk turns, replace prose, then stamp canonical slots with
    recognisable placeholders so tests can key on exact extraction paths."""
    turns = body[0]
    for i, turn in enumerate(turns):
        for slot in range(len(turn)):
            turn[slot] = _walk_replace_prose(turn[slot])
        if turn[2] and turn[2][0]:
            turn[2][0][0] = f"USER_TEXT_{i}"
        if turn[3] and turn[3][0]:
            for j, cand in enumerate(turn[3][0]):
                if cand[1]:
                    cand[1][0] = f"MODEL_TEXT_{i}_{j}"
                if len(cand) > 37 and isinstance(cand[37], list) and cand[37]:
                    inner = cand[37][0]
                    if isinstance(inner, list) and inner and isinstance(inner[0], str):
                        inner[0] = f"MODEL_THOUGHTS_{i}_{j}"
        # Gem name lives at turn[9][0] and (again) at turn[10][1][0].
        if len(turn) > 9 and isinstance(turn[9], list) and turn[9] and isinstance(turn[9][0], str) and turn[9][0]:
            turn[9][0] = "GEM_NAME"
        if len(turn) > 10 and isinstance(turn[10], list) and len(turn[10]) > 1:
            inner_gem = turn[10][1]
            if isinstance(inner_gem, list) and inner_gem and isinstance(inner_gem[0], str) and inner_gem[0]:
                inner_gem[0] = "GEM_NAME"


def redact_list_chats_body(body: list) -> None:
    """body[2] = list of chat rows. Row[1] is title."""
    chats = body[2]
    for i, chat in enumerate(chats):
        if isinstance(chat[1], str) and chat[1]:
            chat[1] = f"CHAT_TITLE_{i}"


def redact_chunk(chunk: str, mode: str) -> str:
    data = json.loads(chunk)
    for entry in data:
        if not isinstance(entry, list) or entry[0] != "wrb.fr":
            continue
        rpcid = entry[1]
        body = json.loads(entry[2])
        if mode == "list_chats" and rpcid == "MaZiqc":
            redact_list_chats_body(body)
        elif mode == "read_chat" and rpcid == "hNvQHb":
            redact_read_chat_body(body)
        entry[2] = json.dumps(body, ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False)


def main() -> None:
    src, mode, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    text = Path(src).read_text()
    chunks = parse_response(text)
    redacted = [redact_chunk(c, mode) if c.startswith("[") else c for c in chunks]
    Path(dst).write_text(rebuild_response(redacted))
    print(f"{src} → {dst}: {len(chunks)} chunks")


if __name__ == "__main__":
    main()
