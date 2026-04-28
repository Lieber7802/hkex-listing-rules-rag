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


class TextLoader(BaseLoader):
    def can_load(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in [".txt"]
    
    def load(self, file_path: Path) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()


class MarkdownLoader(BaseLoader):
    def can_load(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in [".md", ".markdown"]
    
    def load(self, file_path: Path) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()


class PDFLoader(BaseLoader):
    def can_load(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".pdf"
    
    def load(self, file_path: Path) -> str:
        logger.warning(f"PDF loading not fully implemented for {file_path}. Returning empty text.")
        return ""


class DocumentLoader:
    def __init__(self):
        self.loaders: List[BaseLoader] = [
            TextLoader(),
            MarkdownLoader(),
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
        
        raw_text = loader.load(file_path)
        
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
        
        for file_path in dir_path.iterdir():
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
    
    doc_dict = document.model_dump()
    if doc_dict["metadata"]["imported_at"] is not None:
        doc_dict["metadata"]["imported_at"] = doc_dict["metadata"]["imported_at"].isoformat()
    
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
