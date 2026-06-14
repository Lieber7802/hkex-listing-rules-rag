from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import json

from app.schemas.document import Document, DocumentMetadata
from app.core.config import settings
from app.core.logger import logger


class BaseLoader(ABC):
    @abstractmethod
    def load(self, file_path: Path) -> str:
        pass
    
    @abstractmethod
    def can_load(self, file_path: Path) -> bool:
        pass


class TextFileLoader(BaseLoader):
    def can_load(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in [".txt", ".md", ".markdown"]
    
    def load(self, file_path: Path) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()


class PDFLoader(BaseLoader):
    def can_load(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".pdf"

    def load(self, file_path: Path) -> str:
        """Extract text from PDF using PyMuPDF (fitz).

        Strategy:
        1. Extract text page by page
        2. Mark page boundaries with [PAGE N]
        3. Native CJK support (Chinese text)
        4. Graceful fallback on errors
        """
        try:
            import fitz  # pymupdf
        except ImportError:
            raise RuntimeError("pymupdf not installed. Run: pip install pymupdf")

        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        try:
            doc = fitz.open(str(file_path))
        except Exception as e:
            raise RuntimeError(f"Failed to open PDF {file_path}: {e}")

        pages_text = []

        for page_num in range(len(doc)):
            try:
                page = doc[page_num]
                text = page.get_text("text")

                if text.strip():
                    pages_text.append(f"[PAGE {page_num + 1}]\n{text.strip()}")
            except Exception as e:
                logger.warning(f"Failed to extract page {page_num + 1} from {file_path}: {e}")
                continue

        doc.close()

        full_text = "\n\n".join(pages_text)

        if not full_text.strip():
            logger.warning(f"No text extracted from PDF {file_path}. May be image-only.")
            return ""

        logger.info(f"Extracted {len(pages_text)} pages, {len(full_text)} chars from {file_path}")
        return full_text


class DocumentLoader:
    def __init__(self):
        self.loaders: List[BaseLoader] = [
            TextFileLoader(),
            PDFLoader(),
        ]
    
    def get_loader(self, file_path: Path) -> Optional[BaseLoader]:
        for loader in self.loaders:
            if loader.can_load(file_path):
                return loader
        return None
    
    def load_document(self, file_path: Path, document_id: Optional[str] = None) -> Optional[Document]:
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        loader = self.get_loader(file_path)
        if loader is None:
            logger.error(f"No loader found for file type: {file_path.suffix}")
            return None
        
        try:
            raw_text = loader.load(file_path)
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
            return None
        
        if document_id is None:
            document_id = file_path.stem
        
        source_type = file_path.suffix.lower().lstrip(".")
        title = file_path.stem.replace("_", " ").replace("-", " ")
        
        document = Document(
            document_id=document_id,
            source_path=str(file_path),
            source_type=source_type,
            title=title,
            raw_text=raw_text,
            metadata=DocumentMetadata(
                imported_at=datetime.now()
            )
        )
        
        logger.info(f"Loaded document: {document_id} from {file_path}")
        return document
    
    def load_documents_from_directory(self, dir_path: Path) -> List[Document]:
        dir_path = Path(dir_path)
        documents = []

        for file_path in dir_path.rglob("*"):
            if file_path.is_file():
                doc = self.load_document(file_path)
                if doc is not None:
                    documents.append(doc)

        logger.info(f"Loaded {len(documents)} documents from {dir_path}")
        return documents


def save_document(document: Document, output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / f"{document.document_id}.json"
    
    doc_dict = document.model_dump(mode='json')

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc_dict, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved document to: {output_path}")
    return output_path


def load_document_from_json(file_path: Path) -> Document:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if data.get("metadata", {}).get("imported_at"):
        data["metadata"]["imported_at"] = datetime.fromisoformat(data["metadata"]["imported_at"])
    
    return Document(**data)
