import argparse
from pathlib import Path
import json

from app.core.config import settings
from app.core.logger import logger
from app.ingestion.chunker import load_chunks
from app.retrieval.embedder import SentenceTransformerEmbedder, embed_chunks
from app.retrieval.index_store import IndexStore


def build_index(chunks_dir: Path, output_dir: Path):
    chunks_dir = Path(chunks_dir)
    output_dir = Path(output_dir)
    
    all_chunks = []
    for chunk_file in chunks_dir.glob("*_chunks.json"):
        chunks = load_chunks(chunk_file)
        all_chunks.extend(chunks)
    
    if not all_chunks:
        logger.error(f"No chunks found in {chunks_dir}")
        return
    
    logger.info(f"Loaded {len(all_chunks)} chunks from {chunks_dir}")
    
    embeddings = embed_chunks(all_chunks)
    
    index_store = IndexStore()
    index_store.build_indexes(all_chunks, embeddings)
    
    index_store.save(output_dir)
    
    logger.info(f"Index build complete. Saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build vector and BM25 indexes from chunks")
    parser.add_argument("--chunks-dir", type=str, default=str(settings.chunks_dir),
                        help="Directory containing chunk JSON files")
    parser.add_argument("--output-dir", type=str, default=str(settings.indexes_dir),
                        help="Output directory for indexes")
    
    args = parser.parse_args()
    
    build_index(Path(args.chunks_dir), Path(args.output_dir))
