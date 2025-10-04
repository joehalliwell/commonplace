"Search functionality"

from commonplace._config import Config
from commonplace._search._types import Embedder, SearchIndex


def get_store(config: Config) -> SearchIndex:
    """Get the vector store based on the configuration."""
    db_path = config.root / ".commonplace" / "embeddings.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Embedding database not found at {db_path}. Run 'commonplace index' first.")
    from commonplace._search._store import SQLiteVectorStore

    return SQLiteVectorStore(db_path, embedder=get_embedder(config))


def get_embedder(config: Config) -> Embedder:
    """Get the embedder based on the configuration."""
    from commonplace._search._embedder import SentenceTransformersEmbedder

    return SentenceTransformersEmbedder()
