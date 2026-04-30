import re
import json
from pathlib import Path
from typing import List, Optional, Tuple, Union
from dataclasses import dataclass, field

from app.schemas.document import Chunk
from app.core.config import settings
from app.core.logger import logger


@dataclass
class StructureBlock:
    block_type: str
    number: Optional[str]
    title: Optional[str]
    start_pos: int
    end_pos: int
    text: str
    parent_chapter: Optional[str] = None
    parent_section: Optional[str] = None


class StructureAwareChunker:
    def __init__(
        self,
        max_chunk_chars: Optional[int] = None,
        overlap_chars: Optional[int] = None
    ):
        self.max_chunk_chars = max_chunk_chars or settings.chunk_max_chars
        self.overlap_chars = overlap_chars or settings.chunk_overlap_chars
        
        self.chapter_pattern = re.compile(
            r'^(?:Chapter|CHAPTER)\s+(\d{1,3}[A-Za-z]?)\s*[:\-]?\s*(.*?)$',
            re.MULTILINE
        )
        
        self.section_pattern = re.compile(
            r'^(?:Section|SECTION)\s+(\d{1,3}(?:\.\d{1,3})?)\s*[:\-]?\s*(.*?)$',
            re.MULTILINE
        )
        
        self.rule_pattern = re.compile(
            r'^(\d{1,3}[A-Za-z]?(?:\.\d{1,3})?(?:\.\d{1,3})?)\s*[:\-]?\s*(.*?)$',
            re.MULTILINE
        )
        
        self.paragraph_pattern = re.compile(r'\n{2,}')
    
    def extract_structure_blocks(self, text: str) -> List[StructureBlock]:
        blocks = []
        
        chapter_matches = list(self.chapter_pattern.finditer(text))
        for i, match in enumerate(chapter_matches):
            end_pos = chapter_matches[i + 1].start() if i + 1 < len(chapter_matches) else len(text)
            blocks.append(StructureBlock(
                block_type='chapter',
                number=match.group(1).strip(),
                title=match.group(2).strip() if match.group(2) else None,
                start_pos=match.start(),
                end_pos=end_pos,
                text=text[match.start():end_pos]
            ))
        
        rule_matches = list(self.rule_pattern.finditer(text))
        for i, match in enumerate(rule_matches):
            end_pos = rule_matches[i + 1].start() if i + 1 < len(rule_matches) else len(text)
            blocks.append(StructureBlock(
                block_type='rule',
                number=match.group(1).strip(),
                title=match.group(2).strip() if match.group(2) else None,
                start_pos=match.start(),
                end_pos=end_pos,
                text=text[match.start():end_pos]
            ))
        
        if not blocks:
            blocks.append(StructureBlock(
                block_type='document',
                number=None,
                title=None,
                start_pos=0,
                end_pos=len(text),
                text=text
            ))
        
        return blocks
    
    def chunk_block(self, block: StructureBlock, document_id: str, source_path: str) -> List[Chunk]:
        chunks = []
        
        if len(block.text) <= self.max_chunk_chars:
            chunk = self._create_chunk(
                document_id=document_id,
                source_path=source_path,
                block=block,
                text=block.text,
                char_start=block.start_pos,
                char_end=block.end_pos,
                chunk_order=0
            )
            chunks.append(chunk)
            return chunks
        
        paragraphs = self.paragraph_pattern.split(block.text)
        
        current_text = ""
        current_start = block.start_pos
        chunk_order = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if len(para) > self.max_chunk_chars:
                if current_text:
                    chunk = self._create_chunk(
                        document_id=document_id,
                        source_path=source_path,
                        block=block,
                        text=current_text,
                        char_start=current_start,
                        char_end=current_start + len(current_text),
                        chunk_order=chunk_order
                    )
                    chunks.append(chunk)
                    chunk_order += 1
                    current_text = ""
                
                end_idx = 0
                for start_idx in range(0, len(para), self.max_chunk_chars - self.overlap_chars):
                    end_idx = min(start_idx + self.max_chunk_chars, len(para))
                    chunk_text = para[start_idx:end_idx]
                    chunk = self._create_chunk(
                        document_id=document_id,
                        source_path=source_path,
                        block=block,
                        text=chunk_text,
                        char_start=block.start_pos + start_idx,
                        char_end=block.start_pos + end_idx,
                        chunk_order=chunk_order
                    )
                    chunks.append(chunk)
                    chunk_order += 1
                current_text = ""
                current_start = block.start_pos + end_idx
            elif len(current_text) + len(para) + 2 <= self.max_chunk_chars:
                if current_text:
                    current_text += "\n\n" + para
                else:
                    current_text = para
            else:
                if current_text:
                    chunk = self._create_chunk(
                        document_id=document_id,
                        source_path=source_path,
                        block=block,
                        text=current_text,
                        char_start=current_start,
                        char_end=current_start + len(current_text),
                        chunk_order=chunk_order
                    )
                    chunks.append(chunk)
                    chunk_order += 1
                
                overlap_text = current_text[-self.overlap_chars:] if len(current_text) > self.overlap_chars else ""
                current_text = overlap_text + "\n\n" + para if overlap_text else para
                current_start = block.start_pos + block.text.find(para) if para in block.text else block.start_pos
        
        if current_text:
            chunk = self._create_chunk(
                document_id=document_id,
                source_path=source_path,
                block=block,
                text=current_text,
                char_start=current_start,
                char_end=current_start + len(current_text),
                chunk_order=chunk_order
            )
            chunks.append(chunk)
        
        return chunks
    
    def _create_chunk(
        self,
        document_id: str,
        source_path: str,
        block: StructureBlock,
        text: str,
        char_start: int,
        char_end: int,
        chunk_order: int
    ) -> Chunk:
        chunk_id = f"{document_id}:{block.number}:{chunk_order}" if block.number else f"{document_id}:chunk:{chunk_order}"
        
        return Chunk(
            chunk_id=chunk_id,
            document_id=document_id,
            chapter=block.parent_chapter,
            section_title=block.title,
            rule_number=block.number if block.block_type == 'rule' else None,
            parent_section=block.parent_section,
            chunk_order=chunk_order,
            char_start=char_start,
            char_end=char_end,
            source_path=source_path,
            text=text.strip()
        )
    
    def chunk_document(self, document_id: str, text: str, source_path: str) -> List[Chunk]:
        blocks = self.extract_structure_blocks(text)
        
        all_chunks = []
        
        current_chapter = None
        current_section = None
        
        for block in blocks:
            if block.block_type == 'chapter':
                current_chapter = f"Chapter {block.number}"
                if block.title:
                    current_chapter += f": {block.title}"
            
            block.parent_chapter = current_chapter
            block.parent_section = current_section
            
            chunks = self.chunk_block(block, document_id, source_path)
            all_chunks.extend(chunks)
        
        logger.info(f"Created {len(all_chunks)} chunks for document {document_id}")
        return all_chunks


def save_chunks(chunks: List[Chunk], output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not chunks:
        logger.warning("No chunks to save")
        return output_dir
    
    document_id = chunks[0].document_id
    output_path = output_dir / f"{document_id}_chunks.json"
    
    chunks_data = [chunk.model_dump() for chunk in chunks]
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved {len(chunks)} chunks to {output_path}")
    return output_path


def load_chunks(file_path: Path) -> List[Chunk]:
    with open(file_path, "r", encoding="utf-8") as f:
        chunks_data = json.load(f)
    
    return [Chunk(**data) for data in chunks_data]
