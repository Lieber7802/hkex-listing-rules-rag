import argparse
from pathlib import Path
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.logger import logger
from app.ingestion.chunker import load_chunks
from app.retrieval.embedder import BaseEmbedder, get_embedder
from app.retrieval.index_store import IndexStore
from app.schemas.document import Chunk


def _chunk_cache_key(chunk: Chunk, provider: str, model: str) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cache_path(cache_dir: Path, cache_key: str) -> Path:
    return cache_dir / f"{cache_key}.npy"


def _load_cached_embedding(path: Path) -> Optional["np.ndarray"]:
    if not path.exists():
        return None

    import numpy as np

    try:
        return np.load(path).astype(np.float32)
    except Exception as exc:
        logger.warning(f"Ignoring unreadable embedding cache file {path}: {exc}")
        return None


def _save_cached_embedding(path: Path, embedding: "np.ndarray") -> None:
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".npy.tmp")
    with tmp_path.open("wb") as handle:
        np.save(handle, np.asarray(embedding, dtype=np.float32))
    tmp_path.replace(path)


def embed_chunks_with_cache(
    chunks: list[Chunk],
    cache_dir: Path,
    embedder: Optional[BaseEmbedder] = None,
    max_workers: int = 2,
    progress_every: int = 20,
    batch_size: int = 16,
) -> "np.ndarray":
    """Generate embeddings with a persistent per-chunk cache.

    Cache keys include provider, model, chunk_id, and text. If a chunk changes,
    it is automatically re-embedded while unchanged chunks are reused.
    """
    import numpy as np

    if embedder is None:
        embedder = get_embedder()
    if hasattr(embedder, "batch_size"):
        embedder.batch_size = batch_size
    if hasattr(embedder, "max_workers"):
        embedder.max_workers = 1

    provider = settings.embedding_provider
    model = settings.embedding_model
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    embeddings: list[Optional[np.ndarray]] = [None] * len(chunks)
    missing: list[tuple[int, Chunk, Path]] = []

    for idx, chunk in enumerate(chunks):
        path = _cache_path(cache_dir, _chunk_cache_key(chunk, provider, model))
        cached = _load_cached_embedding(path)
        if cached is None:
            missing.append((idx, chunk, path))
        else:
            embeddings[idx] = cached

    logger.info(
        "Embedding cache: %s hit(s), %s miss(es), cache_dir=%s",
        len(chunks) - len(missing),
        len(missing),
        cache_dir,
    )

    if missing:
        progress_every = max(1, progress_every)
        batch_size = max(1, batch_size)
        workers = max(1, max_workers)
        start_time = time.monotonic()

        completed = 0
        batches = [missing[start:start + batch_size] for start in range(0, len(missing), batch_size)]

        def embed_batch(batch: list[tuple[int, Chunk, Path]]):
            batch_texts = [chunk.text for _, chunk, _ in batch]
            batch_embeddings = embedder.embed(batch_texts)
            if len(batch_embeddings) != len(batch):
                raise RuntimeError(
                    f"Embedder returned {len(batch_embeddings)} embeddings for {len(batch)} chunks"
                )
            return batch, batch_embeddings

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(embed_batch, batch) for batch in batches]
            for future in as_completed(futures):
                batch, batch_embeddings = future.result()
                for (idx, _, path), embedding in zip(batch, batch_embeddings):
                    embedding = np.asarray(embedding, dtype=np.float32)
                    _save_cached_embedding(path, embedding)
                    embeddings[idx] = embedding
                    completed += 1

                if completed % progress_every == 0 or completed == len(missing):
                    elapsed = max(time.monotonic() - start_time, 0.001)
                    rate = completed / elapsed
                    remaining = len(missing) - completed
                    eta_seconds = int(remaining / rate) if rate > 0 else 0
                    logger.info(
                        "Embedding progress: %s/%s new, %s/%s total, %.2f chunks/s, ETA %s",
                        completed,
                        len(missing),
                        len(chunks) - len(missing) + completed,
                        len(chunks),
                        rate,
                        _format_duration(eta_seconds),
                    )

    complete_embeddings = [embedding for embedding in embeddings if embedding is not None]
    if len(complete_embeddings) != len(chunks):
        raise RuntimeError("Embedding cache recovery failed: not all chunks have embeddings")

    dimensions = {embedding.shape[0] for embedding in complete_embeddings}
    if len(dimensions) != 1:
        raise ValueError(f"Inconsistent embedding dimensions found: {sorted(dimensions)}")

    result = np.vstack(complete_embeddings).astype(np.float32)
    logger.info(f"Generated embeddings for {len(chunks)} chunks, dimension: {result.shape[1]}")
    return result


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def load_all_chunks(chunks_dir: Path) -> list[Chunk]:
    chunks_dir = Path(chunks_dir)
    all_chunks = []
    for chunk_file in sorted(chunks_dir.glob("*_chunks.json")):
        chunks = load_chunks(chunk_file)
        all_chunks.extend(chunks)
    return all_chunks


def embedding_cache_stats(chunks: list[Chunk], cache_dir: Path) -> dict[str, int]:
    provider = settings.embedding_provider
    model = settings.embedding_model
    cache_dir = Path(cache_dir)
    hits = 0
    misses = 0
    unreadable = 0

    for chunk in chunks:
        path = _cache_path(cache_dir, _chunk_cache_key(chunk, provider, model))
        if not path.exists():
            misses += 1
            continue
        if _load_cached_embedding(path) is None:
            unreadable += 1
            misses += 1
        else:
            hits += 1

    return {
        "total": len(chunks),
        "hits": hits,
        "misses": misses,
        "unreadable": unreadable,
    }


def build_index(
    chunks_dir: Path,
    output_dir: Path,
    resume: bool = True,
    cache_dir: Optional[Path] = None,
    embedding_workers: int = 2,
    progress_every: int = 20,
    embedding_batch_size: int = 16,
):
    chunks_dir = Path(chunks_dir)
    output_dir = Path(output_dir)
    cache_dir = Path(cache_dir) if cache_dir else output_dir / "_embedding_cache"

    all_chunks = load_all_chunks(chunks_dir)

    if not all_chunks:
        logger.error(f"No chunks found in {chunks_dir}")
        return
    
    logger.info(f"Loaded {len(all_chunks)} chunks from {chunks_dir}")
    
    if resume:
        embeddings = embed_chunks_with_cache(
            all_chunks,
            cache_dir=cache_dir,
            max_workers=embedding_workers,
            progress_every=progress_every,
            batch_size=embedding_batch_size,
        )
    else:
        embedder = get_embedder()
        texts = [chunk.text for chunk in all_chunks]
        embeddings = embedder.embed(texts)
    
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
    parser.add_argument("--no-resume", action="store_true",
                        help="Disable embedding cache resume and recompute every vector")
    parser.add_argument("--embedding-cache-dir", type=str, default=None,
                        help="Directory for per-chunk embedding cache; defaults to OUTPUT_DIR/_embedding_cache")
    parser.add_argument("--embedding-workers", type=int, default=2,
                        help="Concurrent embedding workers for cache misses")
    parser.add_argument("--cache-status", action="store_true",
                        help="Print embedding cache hit/miss counts and exit")
    parser.add_argument("--progress-every", type=int, default=20,
                        help="Log embedding progress every N newly completed chunks")
    parser.add_argument("--embedding-batch-size", type=int, default=16,
                        help="Number of missing chunks to embed per Ollama batch request")
    
    args = parser.parse_args()
    
    chunks_dir = Path(args.chunks_dir)
    output_dir = Path(args.output_dir)
    cache_dir = Path(args.embedding_cache_dir) if args.embedding_cache_dir else output_dir / "_embedding_cache"

    if args.cache_status:
        chunks = load_all_chunks(chunks_dir)
        stats = embedding_cache_stats(chunks, cache_dir)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    build_index(
        chunks_dir,
        output_dir,
        resume=not args.no_resume,
        cache_dir=cache_dir,
        embedding_workers=args.embedding_workers,
        progress_every=args.progress_every,
        embedding_batch_size=args.embedding_batch_size,
    )
