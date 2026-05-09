from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    project_name: str = "Agentic RAG for HKEX Listing Rules"
    version: str = "0.1.0"
    
    data_dir: Path = Field(default=Path("data"), description="Base data directory")
    raw_dir: Path = Field(default=Path("data/raw"), description="Raw documents directory")
    processed_dir: Path = Field(default=Path("data/processed"), description="Processed text directory")
    chunks_dir: Path = Field(default=Path("data/chunks"), description="Chunk artifacts directory")
    indexes_dir: Path = Field(default=Path("data/indexes"), description="Index files directory")
    demo_dir: Path = Field(default=Path("data/demo"), description="Demo data directory")
    
    embedding_provider: str = Field(default="ollama", description="Embedding provider: ollama or sentence-transformers")
    embedding_model: str = Field(default="bge-m3", description="Embedding model name (for ollama: bge-m3, bge-large, etc.)")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", description="Ollama API base URL")
    
    llm_provider: str = Field(default="deepseek", description="LLM provider: deepseek, openai, etc.")
    llm_model: str = Field(default="deepseek-reasoner", description="LLM model name")
    llm_api_key: Optional[str] = Field(default=None, description="LLM API key")
    llm_base_url: Optional[str] = Field(default="https://api.deepseek.com", description="LLM base URL")
    
    retrieval_top_k_bm25: int = Field(default=20, description="Top-k for BM25 retrieval")
    retrieval_top_k_dense: int = Field(default=20, description="Top-k for dense retrieval")
    retrieval_top_k_final: int = Field(default=10, description="Final top-k after fusion")
    bm25_weight: float = Field(default=0.4, description="Weight for BM25 scores (legacy, kept for backward compat)")
    dense_weight: float = Field(default=0.6, description="Weight for dense scores (legacy, kept for backward compat)")
    rrf_k: int = Field(default=60, description="RRF smoothing constant k (default 60 per original paper)")
    
    chunk_max_chars: int = Field(default=1500, description="Maximum characters per chunk")
    chunk_overlap_chars: int = Field(default=100, description="Character overlap for long sections")

    # Session / multi-turn conversation settings
    session_ttl_minutes: int = Field(default=60, description="Session TTL in minutes before expiry")
    session_max_turns: int = Field(default=50, description="Maximum turns to keep per session")
    session_storage_dir: Path = Field(default=Path("data/sessions"), description="JSONL session storage directory")
    session_history_window: int = Field(default=5, description="Number of recent Q&A pairs to inject into LLM context")

    log_level: str = Field(default="INFO", description="Logging level")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for dir_path in [self.data_dir, self.raw_dir, self.processed_dir, self.chunks_dir, self.indexes_dir, self.demo_dir, self.session_storage_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)


settings = Settings()
