from abc import ABC, abstractmethod
from typing import List, Optional
import numpy as np
import httpx
import concurrent.futures

from app.schemas.document import Chunk
from app.core.config import settings
from app.core.logger import logger


class BaseEmbedder(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        pass

    @abstractmethod
    def embed_single(self, text: str) -> np.ndarray:
        pass


class OllamaEmbedder(BaseEmbedder):
    def __init__(self, model_name: Optional[str] = None, base_url: Optional[str] = None, batch_size: int = 50, max_workers: int = 8):
        self.model_name = model_name or settings.embedding_model
        self.base_url = base_url or settings.ollama_base_url
        self.dimension = 1024
        self.batch_size = batch_size
        self.max_workers = max_workers
        logger.info(f"Initialized Ollama embedder: {self.model_name} at {self.base_url} (workers={max_workers}, batch={batch_size})")

    def embed(self, texts: List[str]) -> np.ndarray:
        """Embed texts using concurrent requests to Ollama for speed."""
        total = len(texts)
        embeddings = [None] * total

        def _embed_one(idx_text):
            idx, text = idx_text
            return idx, self._embed_single_request(text)

        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_embed_one, (i, t)): i for i, t in enumerate(texts)}
            for future in concurrent.futures.as_completed(futures):
                idx, embedding = future.result()
                embeddings[idx] = embedding
                completed += 1
                if completed % 200 == 0 or completed == total:
                    logger.info(f"Embedding progress: {completed}/{total} ({100*completed//total}%)")

        if embeddings and len(embeddings[0]) > 0:
            self.dimension = len(embeddings[0])

        return np.array(embeddings, dtype=np.float32)

    def _embed_single_request(self, text: str) -> List[float]:
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model_name,
                        "prompt": text
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data.get("embedding", [])
        except Exception as e:
            logger.error(f"Ollama embedding error: {e}")
            return [0.0] * self.dimension

    def embed_single(self, text: str) -> np.ndarray:
        embedding = self._embed_single_request(text)
        return np.array(embedding, dtype=np.float32)


class SentenceTransformerEmbedder(BaseEmbedder):
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.embedding_model
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Loaded embedding model: {self.model_name}")
        except ImportError:
            logger.warning("sentence_transformers not installed. Using mock embedder.")
            self.model = None
    
    def embed(self, texts: List[str]) -> np.ndarray:
        if self.model is None:
            return np.random.randn(len(texts), 384).astype(np.float32)
        
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings
    
    def embed_single(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


def get_embedder(provider: Optional[str] = None) -> BaseEmbedder:
    provider = provider or settings.embedding_provider
    
    if provider == "ollama":
        return OllamaEmbedder()
    else:
        return SentenceTransformerEmbedder()


def embed_chunks(chunks: List[Chunk], embedder: Optional[BaseEmbedder] = None) -> np.ndarray:
    if embedder is None:
        embedder = get_embedder()
    
    texts = [chunk.text for chunk in chunks]
    embeddings = embedder.embed(texts)
    
    logger.info(f"Generated embeddings for {len(chunks)} chunks, dimension: {embeddings.shape[1]}")
    return embeddings