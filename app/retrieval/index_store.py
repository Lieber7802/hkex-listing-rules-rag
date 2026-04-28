import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from app.schemas.document import Chunk
from app.core.config import settings
from app.core.logger import logger


class VectorIndex:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.index = None
        self.chunk_ids: List[str] = []
        self.chunks: List[Chunk] = []
    
    def build(self, chunks: List[Chunk], embeddings: np.ndarray):
        import faiss
        
        self.chunks = chunks
        self.chunk_ids = [chunk.chunk_id for chunk in chunks]
        
        embeddings = embeddings.astype(np.float32)
        
        n_vectors = embeddings.shape[0]
        self.index = faiss.IndexFlatIP(self.dimension)
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        
        logger.info(f"Built FAISS index with {n_vectors} vectors of dimension {self.dimension}")
    
    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
        import faiss
        
        if self.index is None:
            return []
        
        query_embedding = query_embedding.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(query_embedding)
        
        scores, indices = self.index.search(query_embedding, top_k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < len(self.chunk_ids):
                results.append((self.chunk_ids[idx], float(score)))
        
        return results
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[Chunk]:
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk
        return None
    
    def save(self, path: Path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        import faiss
        faiss.write_index(self.index, str(path / 'faiss_index.bin'))
        
        chunks_data = [chunk.model_dump() for chunk in self.chunks]
        with open(path / 'chunks.json', 'w', encoding='utf-8') as f:
            json.dump(chunks_data, f, ensure_ascii=False, indent=2)
        
        with open(path / 'chunk_ids.pkl', 'wb') as f:
            pickle.dump(self.chunk_ids, f)
        
        logger.info(f"Saved vector index to {path}")
    
    @classmethod
    def load(cls, path: Path) -> 'VectorIndex':
        path = Path(path)
        
        import faiss
        index = cls()
        index.index = faiss.read_index(str(path / 'faiss_index.bin'))
        index.dimension = index.index.d
        
        with open(path / 'chunks.json', 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        index.chunks = [Chunk(**data) for data in chunks_data]
        
        with open(path / 'chunk_ids.pkl', 'rb') as f:
            index.chunk_ids = pickle.load(f)
        
        logger.info(f"Loaded vector index from {path}")
        return index


class IndexStore:
    def __init__(self):
        self.vector_index: Optional[VectorIndex] = None
        self.bm25_index = None
        self.chunks: List[Chunk] = []
    
    def build_indexes(self, chunks: List[Chunk], embeddings: np.ndarray):
        from app.retrieval.bm25 import BM25Index
        
        self.chunks = chunks
        
        self.vector_index = VectorIndex(dimension=embeddings.shape[1])
        self.vector_index.build(chunks, embeddings)
        
        self.bm25_index = BM25Index()
        self.bm25_index.fit(chunks)
        
        logger.info(f"Built all indexes for {len(chunks)} chunks")
    
    def save(self, path: Path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        if self.vector_index:
            self.vector_index.save(path / 'vector')
        
        if self.bm25_index:
            self.bm25_index.save(path / 'bm25')
        
        logger.info(f"Saved index store to {path}")
    
    @classmethod
    def load(cls, path: Path) -> 'IndexStore':
        store = cls()
        
        vector_path = path / 'vector'
        if vector_path.exists():
            store.vector_index = VectorIndex.load(vector_path)
            store.chunks = store.vector_index.chunks
        
        bm25_path = path / 'bm25'
        if bm25_path.exists():
            from app.retrieval.bm25 import BM25Index
            store.bm25_index = BM25Index.load(bm25_path)
        
        logger.info(f"Loaded index store from {path}")
        return store
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[Chunk]:
        if self.vector_index:
            return self.vector_index.get_chunk_by_id(chunk_id)
        return None