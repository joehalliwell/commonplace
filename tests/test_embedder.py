"""Tests for text embedding."""

import numpy as np
import pytest

from commonplace._search._embedder import SentenceTransformersEmbedder


@pytest.fixture
def embedder():
    """Create an embedder instance."""
    return SentenceTransformersEmbedder()


def test_model_id(embedder):
    """Test that model_id is correctly set."""
    assert embedder.model_id == "sentence-transformers:all-MiniLM-L6-v2"


def test_single_embedding(embedder):
    """Test embedding a single text."""
    text = "This is a test sentence."
    embedding = embedder.embed(text)

    assert isinstance(embedding, np.ndarray)
    assert embedding.dtype == np.float32
    assert len(embedding.shape) == 1
    assert embedding.shape[0] == 384  # all-MiniLM-L6-v2 dimension


def test_batch_embedding(embedder):
    """Test embedding multiple texts."""
    texts = ["First sentence.", "Second sentence.", "Third sentence."]
    embeddings = embedder.embed_batch(texts)

    assert isinstance(embeddings, np.ndarray)
    assert embeddings.dtype == np.float32
    assert embeddings.shape == (3, 384)


def test_similar_texts_have_similar_embeddings(embedder):
    """Test that similar texts produce similar embeddings."""
    text1 = "The cat sat on the mat."
    text2 = "A cat was sitting on a mat."
    text3 = "Python is a programming language."

    emb1 = embedder.embed(text1)
    emb2 = embedder.embed(text2)
    emb3 = embedder.embed(text3)

    # Cosine similarity
    def cosine_sim(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    sim_12 = cosine_sim(emb1, emb2)
    sim_13 = cosine_sim(emb1, emb3)

    # Similar texts should be more similar than dissimilar ones
    assert sim_12 > sim_13
    assert sim_12 > 0.5  # Should be reasonably similar
