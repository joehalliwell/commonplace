"""Tests for text embedding."""

import numpy as np
import pytest

from commonplace._search._embedder import FastEmbedEmbedder, get_embedder


class FakeTextEmbedding:
    """Stands in for fastembed's model, recording exactly the text it is asked to embed."""

    def __init__(self):
        self.seen: list[str] = []

    def embed(self, texts):
        texts = [texts] if isinstance(texts, str) else list(texts)
        self.seen.extend(texts)
        for text in texts:
            yield np.array([len(text), 1.0], dtype=np.float32)


def _fastembed(model_name: str) -> tuple[FastEmbedEmbedder, FakeTextEmbedding]:
    embedder = FastEmbedEmbedder(model_name)
    embedder.__dict__["model"] = fake = FakeTextEmbedding()
    return embedder, fake


def test_fastembed_embeds_one_document_as_it_does_a_batch():
    """`index` embeds in batches; a document embedded alone must land in the same place."""
    embedder, fake = _fastembed("snowflake/snowflake-arctic-embed-xs")

    assert np.array_equal(embedder.embed_doc("Prefers tea."), embedder.embed_docs(["Prefers tea."])[0])
    assert fake.seen == ["Prefers tea.", "Prefers tea."]


@pytest.mark.parametrize("model_name", ["BAAI/bge-small-en-v1.5", "snowflake/snowflake-arctic-embed-xs"])
def test_fastembed_query_carries_the_models_retrieval_instruction(model_name):
    """Both were trained with it on short queries; E5's `query: ` is another family's convention."""
    embedder, fake = _fastembed(model_name)

    embedder.embed_query("tea")

    assert fake.seen == ["Represent this sentence for searching relevant passages: tea"]


def test_fastembed_query_for_a_model_without_an_instruction_is_bare():
    embedder, fake = _fastembed("jinaai/jina-embeddings-v2-small-en")

    embedder.embed_query("tea")

    assert fake.seen == ["tea"]


@pytest.fixture
def embedder():
    """Create an embedder instance."""
    return get_embedder()


def test_single_embedding(embedder):
    """Test embedding a single text."""
    text = "This is a test sentence."
    embedding = embedder.embed_doc(text)

    assert isinstance(embedding, np.ndarray)
    assert embedding.dtype == np.float32
    assert len(embedding.shape) == 1
    assert embedding.shape[0] == 384  # all-MiniLM-L6-v2 dimension


def test_batch_embedding(embedder):
    """Test embedding multiple texts."""
    texts = ["First sentence.", "Second sentence.", "Third sentence."]
    embeddings = embedder.embed_docs(texts)

    assert isinstance(embeddings, np.ndarray)
    assert embeddings.dtype == np.float32
    assert embeddings.shape == (3, 384)


def test_similar_texts_have_similar_embeddings(embedder):
    """Test that similar texts produce similar embeddings."""
    text1 = "The cat sat on the mat."
    text2 = "A cat was sitting on a mat."
    text3 = "Python is a programming language."

    emb1 = embedder.embed_doc(text1)
    emb2 = embedder.embed_doc(text2)
    emb3 = embedder.embed_doc(text3)

    # Cosine similarity
    def cosine_sim(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    sim_12 = cosine_sim(emb1, emb2)
    sim_13 = cosine_sim(emb1, emb3)

    # Similar texts should be more similar than dissimilar ones
    assert sim_12 > sim_13
    assert sim_12 > 0.5  # Should be reasonably similar
