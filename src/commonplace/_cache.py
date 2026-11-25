"""The repository's cache database, `.commonplace/cache/index.db`: its schema, the version stamped on it, and the
migrations from every older version. The search store and the graph each read and write their own tables in it.
"""

import sqlite3
from pathlib import Path

from commonplace._config import CACHE
from commonplace._logging import logger

#: Where the cache database lives, relative to the root; not committed.
INDEX_DB = CACHE / "index.db"

#: The schema this database is written in, stamped as `user_version`. Version 1 predates the stamp: a database
#: whose every chunk named its own model, path and ref. Version 2 names a note once, in `notes`, which
#: also records a note that yields no chunks, so it is visited once rather than on every run. Version 3
#: stores embeddings at half precision, halving the bulk of the file; cosine ranking never needed more.
#: Version 4 names a note's version by git's id for its content, `content_id`, where v3 named the commit that
#: last changed it: v3's versions are stale on the next run and replaced, keeping their embeddings. Version 5 adds
#: the graph: each file version's labels, and its edges, each landed on `to_node` against the files `graph_state`
#: records, so a pass over the graph needn't read the files, nor a query resolve the links.
INDEX_VERSION = 5

_NOTES_DDL = """
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    model_id TEXT NOT NULL,
    path TEXT NOT NULL,
    content_id TEXT NOT NULL,
    UNIQUE(model_id, path, content_id)
);
"""

_CHUNKS_DDL = """
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    section TEXT NOT NULL,
    text TEXT NOT NULL,
    offset INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    UNIQUE(note_id, offset)
);
"""

#: What keeps full-text search in step with `chunks`.
_TRIGGERS_DDL = """
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

_GRAPH_DDL = """
CREATE TABLE graph_files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    content_id TEXT NOT NULL,
    landed INTEGER NOT NULL DEFAULT 0,
    UNIQUE(path, content_id)
);
CREATE TABLE graph_labels (
    file_id INTEGER NOT NULL REFERENCES graph_files(id) ON DELETE CASCADE,
    label TEXT NOT NULL
);
CREATE INDEX graph_labels_by_file ON graph_labels(file_id);
CREATE TABLE graph_edges (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES graph_files(id) ON DELETE CASCADE,
    from_node TEXT NOT NULL,
    to_node TEXT,
    line INTEGER NOT NULL,
    target TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX graph_edges_by_file ON graph_edges(file_id);
CREATE INDEX graph_edges_by_to_node ON graph_edges(to_node);
CREATE TABLE graph_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_FRESH = f"""
BEGIN;
{_NOTES_DDL}
{_CHUNKS_DDL}
CREATE VIRTUAL TABLE chunks_fts USING fts5(text, section, content=chunks, content_rowid=id);
{_TRIGGERS_DDL}
{_GRAPH_DDL}
PRAGMA user_version = {INDEX_VERSION};
COMMIT;
"""

# Chunk ids are kept, so the external-content full-text index still points at the right rows, and no
# embedding is recomputed. The copy runs before the new triggers exist, or it would re-add every row to
# the full-text index; dropping v1's table takes its own indexes and triggers with it. Its `notes` is
# v2's, which v3 kept and v4 renamed a column of.
_MIGRATE_V1 = f"""
BEGIN;
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    model_id TEXT NOT NULL,
    path TEXT NOT NULL,
    ref TEXT NOT NULL,
    UNIQUE(model_id, path, ref)
);
INSERT INTO notes (model_id, path, ref)
    SELECT model_id, path, ref FROM chunks GROUP BY model_id, path, ref ORDER BY MIN(id);
ALTER TABLE chunks RENAME TO chunks_v1;
{_CHUNKS_DDL}
INSERT INTO chunks (id, note_id, section, text, offset, embedding)
    SELECT c.id, n.id, c.section, c.text, c.offset, c.embedding
    FROM chunks_v1 c JOIN notes n ON (n.model_id, n.path, n.ref) = (c.model_id, c.path, c.ref);
DROP TABLE chunks_v1;
{_TRIGGERS_DDL}
PRAGMA user_version = 2;
COMMIT;
"""

# The same rebuild as v1's, and for the same reasons; `half` is registered on the connection.
_MIGRATE_V2 = f"""
BEGIN;
ALTER TABLE chunks RENAME TO chunks_v2;
{_CHUNKS_DDL}
INSERT INTO chunks (id, note_id, section, text, offset, embedding)
    SELECT id, note_id, section, text, offset, half(embedding) FROM chunks_v2;
DROP TABLE chunks_v2;
{_TRIGGERS_DDL}
PRAGMA user_version = 3;
COMMIT;
"""

# The commit ids v3 holds are kept, not dropped: replacing them on the next run lends their embeddings.
_MIGRATE_V3 = """
BEGIN;
ALTER TABLE notes RENAME COLUMN ref TO content_id;
PRAGMA user_version = 4;
COMMIT;
"""

_MIGRATE_V4 = f"""
BEGIN;
{_GRAPH_DDL}
PRAGMA user_version = 5;
COMMIT;
"""

#: version -> the script that takes an index from it to the next.
_MIGRATIONS = {1: _MIGRATE_V1, 2: _MIGRATE_V2, 3: _MIGRATE_V3, 4: _MIGRATE_V4}


def connect(path: Path) -> sqlite3.Connection:
    """A connection to the cache database at `path`, created fresh, migrated in place, or refused if newer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        _open_schema(conn, path)
    except Exception:
        conn.close()
        raise
    # Per connection, and off by default: without it, removing a note would orphan its chunks.
    conn.execute("PRAGMA foreign_keys = ON")
    # Readers needn't wait for `index`'s writes, nor it for theirs; the mode is the file's, so this sets it once.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _open_schema(conn: sqlite3.Connection, path: Path) -> None:
    """Create a fresh index, migrate an older one in place, or refuse one newer than this release."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == INDEX_VERSION:
        return
    if version > INDEX_VERSION:
        raise RuntimeError(
            f"{path} is schema v{version}, newer than this release's v{INDEX_VERSION}: upgrade, or delete it"
        )
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunks'").fetchone():
        conn.executescript(_FRESH)
        return
    logger.info(f"Migrating {path} from schema v{max(version, 1)} to v{INDEX_VERSION}")
    conn.create_function("half", 1, _half, deterministic=True)
    # Version 1 predates the stamp, so reads as 0.
    for step in range(max(version, 1), INDEX_VERSION):
        conn.executescript(_MIGRATIONS[step])
    # Migrating from v1 or v2 rebuilds `chunks` smaller, and only a vacuum gives the space back; later ones add.
    if version < 3:
        conn.execute("VACUUM")


def _half(blob: bytes) -> bytes:
    """An embedding as v2 stored it, float32, as v3 does: float16."""
    import numpy as np  # Only a migration from v2 needs it, and every command that reads links opens this database.

    return np.frombuffer(blob, np.float32).astype(np.float16).tobytes()
