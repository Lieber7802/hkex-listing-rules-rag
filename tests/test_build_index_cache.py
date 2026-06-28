import numpy as np

from app.retrieval.embedder import BaseEmbedder
from app.schemas.document import Chunk
from scripts.build_index import embed_chunks_with_cache


class FakeEmbedder(BaseEmbedder):
    def __init__(self):
        self.calls = 0

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self.embed_single(text) for text in texts])

    def embed_single(self, text: str) -> np.ndarray:
        self.calls += 1
        return np.array([len(text), self.calls], dtype=np.float32)


def make_chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="doc",
        source_path="source.md",
        text=text,
    )


def test_embed_chunks_with_cache_reuses_completed_embeddings(tmp_path):
    chunks = [
        make_chunk("doc:chunk:0", "alpha"),
        make_chunk("doc:chunk:1", "beta"),
    ]
    embedder = FakeEmbedder()

    first = embed_chunks_with_cache(chunks, tmp_path, embedder=embedder, max_workers=1)
    assert embedder.calls == 2

    second = embed_chunks_with_cache(chunks, tmp_path, embedder=embedder, max_workers=1)

    assert embedder.calls == 2
    np.testing.assert_array_equal(second, first)


def test_embed_chunks_with_cache_reembeds_changed_chunk_text(tmp_path):
    embedder = FakeEmbedder()
    chunk = make_chunk("doc:chunk:0", "alpha")
    embed_chunks_with_cache([chunk], tmp_path, embedder=embedder, max_workers=1)

    changed_chunk = make_chunk("doc:chunk:0", "alpha changed")
    changed = embed_chunks_with_cache([changed_chunk], tmp_path, embedder=embedder, max_workers=1)

    assert embedder.calls == 2
    assert changed[0, 0] == len("alpha changed")
