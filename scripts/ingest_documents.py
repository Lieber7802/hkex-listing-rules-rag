import argparse
from pathlib import Path
import json

from app.core.config import settings
from app.core.logger import logger
from app.ingestion.loader import DocumentLoader, save_document
from app.ingestion.cleaner import clean_document_text
from app.ingestion.chunker import StructureAwareChunker, save_chunks


def ingest_documents(
    input_dir: Path,
    processed_dir: Path,
    chunks_dir: Path
):
    input_dir = Path(input_dir)
    processed_dir = Path(processed_dir)
    chunks_dir = Path(chunks_dir)
    
    processed_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    
    loader = DocumentLoader()
    chunker = StructureAwareChunker()
    
    documents = loader.load_documents_from_directory(input_dir)
    
    if not documents:
        logger.warning(f"No documents found in {input_dir}")
        return
    
    all_chunks = []
    
    for doc in documents:
        doc.cleaned_text = clean_document_text(doc.raw_text, preserve_rule_numbers=True)
        
        save_document(doc, processed_dir)
        
        chunks = chunker.chunk_document(
            document_id=doc.document_id,
            text=doc.cleaned_text,
            source_path=doc.source_path
        )
        
        all_chunks.extend(chunks)
        
        save_chunks(chunks, chunks_dir)
    
    logger.info(f"Ingestion complete. Processed {len(documents)} documents, created {len(all_chunks)} chunks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest documents into the knowledge base")
    parser.add_argument("--input-dir", type=str, default=str(settings.raw_dir),
                        help="Directory containing raw documents")
    parser.add_argument("--processed-dir", type=str, default=str(settings.processed_dir),
                        help="Output directory for processed documents")
    parser.add_argument("--chunks-dir", type=str, default=str(settings.chunks_dir),
                        help="Output directory for chunks")
    
    args = parser.parse_args()
    
    ingest_documents(
        Path(args.input_dir),
        Path(args.processed_dir),
        Path(args.chunks_dir)
    )
