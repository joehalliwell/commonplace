"""Importer for the `gemini-memory-wire.jsonl.gz` archive produced by [[GeminiMemoryFetcher]].

The archive holds one `ZKcapf` entry whose body is `[items, token]`, each item
`[id, text, [created s, ns], None, [updated s, ns], None, None, None, None, int, int]`.
Slots are indexed without defaults, so drift fails loudly.
"""

from pathlib import Path

from commonplace._import._base import BaseWireImporter
from commonplace._import._gemini import _extract_rpc_body
from commonplace._import._types import Snapshot
from commonplace._types import Note, RepoPath
from commonplace._wire import read_entries

RPC_LIST_SAVED_INFO = "ZKcapf"


class GeminiMemoryImporter(BaseWireImporter):
    source: str = "gemini-memory"
    tree: Path = Path("memory") / "gemini"

    def snapshot(self, path: Path) -> Snapshot:
        [entry] = read_entries(path)
        body = _extract_rpc_body(entry["response"], RPC_LIST_SAVED_INFO)
        if body is None:
            raise RuntimeError(f"{RPC_LIST_SAVED_INFO} in '{path}' has a null wrb.fr body")
        # By creation, so an edit changes its own line rather than moving it to the top.
        items = sorted(body[0], key=lambda item: item[2])
        bullets = "".join(f"- {item[1].replace('\n', '\n  ')}\n" for item in items)
        title = "Saved info"
        note = Note.compose(RepoPath(self.tree / "saved-info.md"), "Memory", title, f"# {title}\n\n{bullets}")
        return Snapshot([note])
