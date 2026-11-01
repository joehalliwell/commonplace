"""Regenerate the example search indexes in this directory: `just index-examples`.

One database per index schema version, each holding the same chunks, so tests can
assert that every version we have ever written still opens to the same index.
The `any_index_version` fixture is parametrised over the full version range, so a
bump without a matching example here fails the suite.

Each version's DDL is written out verbatim rather than borrowed from the store,
which moves on: these files are the evidence of what each version looked like.
Embeddings come from `ExampleEmbedder`, so no model is needed to build or read them.
"""

import sqlite3
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

OUT = Path(__file__).parent

REF_A = "a" * 40
REF_B = "b" * 40

#: (path, ref, section, text, offset): two chunks of one note, one of another.
CHUNKS = [
    ("notes/tea.md", REF_A, "Tea", "Prefers tea to coffee.", 0),
    ("notes/tea.md", REF_A, "Tea / Brewing", "Steep for four minutes.", 40),
    ("notes/walks.md", REF_B, "Walks", "Long walks along the river.", 0),
]


class ExampleEmbedder:
    """A deterministic four-dimensional embedder: enough to rank, nothing to download."""

    model_id = "example:shape-4"

    def embed_doc(self, text: str) -> NDArray[np.float32]:
        return np.array(
            [len(text), sum(c in "aeiou" for c in text), text.count(" "), 1.0],
            dtype=np.float32,
        )

    def embed_docs(self, texts: list[str]) -> NDArray[np.float32]:
        return np.array([self.embed_doc(text) for text in texts], dtype=np.float32)

    def embed_query(self, query: str) -> NDArray[np.float32]:
        return self.embed_doc(query)


V1_DDL = """
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    path TEXT NOT NULL,
    ref TEXT NOT NULL,
    section TEXT NOT NULL,
    text TEXT NOT NULL,
    offset INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    UNIQUE(model_id, path, ref, offset)
);
CREATE INDEX idx_path_ref ON chunks(path, ref);
CREATE INDEX idx_model ON chunks(model_id);
CREATE VIRTUAL TABLE chunks_fts USING fts5(text, section, content=chunks, content_rowid=id);
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, section) VALUES (new.id, new.text, new.section);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section) VALUES('delete', old.id, old.text, old.section);
END;
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section) VALUES('delete', old.id, old.text, old.section);
    INSERT INTO chunks_fts(rowid, text, section) VALUES (new.id, new.text, new.section);
END;
"""


def _write_v1(conn: sqlite3.Connection) -> None:
    """The pre-versioning schema: no `user_version`, every chunk naming its own note."""
    conn.executescript(V1_DDL)
    embedder = ExampleEmbedder()
    conn.executemany(
        "INSERT INTO chunks (model_id, path, ref, section, text, offset, embedding) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (embedder.model_id, path, ref, section, text, offset, embedder.embed_doc(text).tobytes())
            for path, ref, section, text, offset in CHUNKS
        ],
    )


#: version -> writer
EXAMPLES = {1: _write_v1}


def main() -> None:
    for version, write in EXAMPLES.items():
        path = OUT / f"index-v{version}.db"
        path.unlink(missing_ok=True)
        with sqlite3.connect(path) as conn:
            write(conn)
        conn.close()
        print(f"wrote {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
