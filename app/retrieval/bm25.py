import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from app.schemas.document import Chunk
from app.core.config import settings
from app.core.logger import logger


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avgdl = 0
        self.doc_freqs: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_len: List[int] = []
        self.doc_ids: List[str] = []
        self.doc_texts: List[str] = []
    
    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        tokens = []
        current_token = []
        for char in text:
            if char.isalnum():
                current_token.append(char)
            else:
                if current_token:
                    tokens.append(''.join(current_token))
                    current_token = []
        if current_token:
            tokens.append(''.join(current_token))
        return tokens
    
    def fit(self, chunks: List[Chunk]):
        self.doc_ids = [chunk.chunk_id for chunk in chunks]
        self.doc_texts = [chunk.text for chunk in chunks]
        
        tokenized_corpus = [self._tokenize(chunk.text) for chunk in chunks]
        
        self.corpus_size = len(tokenized_corpus)
        self.doc_len = [len(doc) for doc in tokenized_corpus]
        self.avgdl = sum(self.doc_len) / self.corpus_size if self.corpus_size > 0 else 0
        
        df: Dict[str, int] = {}
        for doc in tokenized_corpus:
            seen = set()
            for word in doc:
                if word not in seen:
                    df[word] = df.get(word, 0) + 1
                    seen.add(word)
        self.doc_freqs = df
        
        for word, freq in self.doc_freqs.items():
            self.idf[word] = np.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1)
        
        logger.info(f"Built BM25 index for {self.corpus_size} documents")
    
    def get_scores(self, query: str) -> np.ndarray:
        query_tokens = self._tokenize(query)
        scores = np.zeros(self.corpus_size)
        
        tokenized_corpus = [self._tokenize(text) for text in self.doc_texts]
        
        for i, doc in enumerate(tokenized_corpus):
            score = 0.0
            doc_len = self.doc_len[i]
            for q_token in query_tokens:
                if q_token not in self.idf:
                    continue
                
                tf = doc.count(q_token)
                idf = self.idf[q_token]
                
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                score += idf * numerator / denominator
            
            scores[i] = score
        
        return scores
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        scores = self.get_scores(query)
        
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = [(self.doc_ids[i], float(scores[i])) for i in top_indices if scores[i] > 0]
        return results
    
    def save(self, path: Path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        data = {
            'k1': self.k1,
            'b': self.b,
            'corpus_size': self.corpus_size,
            'avgdl': self.avgdl,
            'doc_freqs': self.doc_freqs,
            'idf': self.idf,
            'doc_len': self.doc_len,
            'doc_ids': self.doc_ids,
            'doc_texts': self.doc_texts
        }
        
        with open(path / 'bm25_index.pkl', 'wb') as f:
            pickle.dump(data, f)
        
        logger.info(f"Saved BM25 index to {path}")
    
    @classmethod
    def load(cls, path: Path) -> 'BM25Index':
        path = Path(path)
        
        with open(path / 'bm25_index.pkl', 'rb') as f:
            data = pickle.load(f)
        
        index = cls(k1=data['k1'], b=data['b'])
        index.corpus_size = data['corpus_size']
        index.avgdl = data['avgdl']
        index.doc_freqs = data['doc_freqs']
        index.idf = data['idf']
        index.doc_len = data['doc_len']
        index.doc_ids = data['doc_ids']
        index.doc_texts = data['doc_texts']
        
        logger.info(f"Loaded BM25 index from {path}")
        return index