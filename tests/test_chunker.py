import pytest
from app.ingestion.chunker import StructureAwareChunker, StructureBlock, save_chunks, load_chunks
from app.schemas.document import Chunk
from pathlib import Path
import tempfile
import json


class TestStructureAwareChunker:
    
    def test_extract_structure_blocks_finds_chapters(self):
        chunker = StructureAwareChunker()
        text = "Chapter 14: Connected Transactions\n\nSome content here.\n\nChapter 15: Other Rules\n\nMore content."
        blocks = chunker.extract_structure_blocks(text)
        
        assert len(blocks) == 2
        assert blocks[0].block_type == 'chapter'
        assert blocks[0].number == '14'
        assert blocks[1].number == '15'
    
    def test_extract_structure_blocks_finds_rules(self):
        chunker = StructureAwareChunker()
        text = "14A.35: Disclosure Requirements\n\nContent for rule.\n\n14A.36: Additional Requirements\n\nMore content."
        blocks = chunker.extract_structure_blocks(text)
        
        assert len(blocks) == 2
        assert blocks[0].block_type == 'rule'
        assert blocks[0].number == '14A.35'
        assert blocks[1].number == '14A.36'
    
    def test_chunk_small_block_creates_single_chunk(self):
        chunker = StructureAwareChunker(max_chunk_chars=1000)
        text = "14A.35: Short rule\n\nThis is a short rule content."
        blocks = chunker.extract_structure_blocks(text)
        
        chunks = chunker.chunk_block(
            block=blocks[0],
            document_id="test-doc",
            source_path="test.md"
        )
        
        assert len(chunks) == 1
        assert chunks[0].rule_number == '14A.35'
        assert chunks[0].chunk_order == 0
    
    def test_chunk_large_block_splits_into_multiple(self):
        chunker = StructureAwareChunker(max_chunk_chars=100, overlap_chars=20)
        text = "14A.35: Long rule\n\n" + "Content " * 50
        blocks = chunker.extract_structure_blocks(text)
        
        chunks = chunker.chunk_block(
            block=blocks[0],
            document_id="test-doc",
            source_path="test.md"
        )
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text) <= chunker.max_chunk_chars + chunker.overlap_chars
    
    def test_chunk_document_returns_list_of_chunks(self):
        chunker = StructureAwareChunker()
        text = "Chapter 14A\n\n14A.35: First rule\n\nContent here.\n\n14A.36: Second rule\n\nMore content."
        
        chunks = chunker.chunk_document(
            document_id="hkex-ct",
            text=text,
            source_path="data/raw/test.md"
        )
        
        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.document_id == "hkex-ct" for c in chunks)
    
    def test_chunk_id_format(self):
        chunker = StructureAwareChunker()
        text = "14A.35: Test rule\n\nContent."
        blocks = chunker.extract_structure_blocks(text)
        chunks = chunker.chunk_block(
            block=blocks[0],
            document_id="hkex-ct-001",
            source_path="test.md"
        )
        
        assert ":" in chunks[0].chunk_id
        assert "hkex-ct-001" in chunks[0].chunk_id
        assert "14A.35" in chunks[0].chunk_id

    def test_chunk_document_makes_duplicate_rule_ids_unique(self):
        chunker = StructureAwareChunker()
        text = "1. First numbered paragraph\n\nContent.\n\n1. Second numbered paragraph\n\nMore content."

        chunks = chunker.chunk_document(
            document_id="duplicated-rules",
            text=text,
            source_path="test.md"
        )

        chunk_ids = [chunk.chunk_id for chunk in chunks]
        assert len(chunk_ids) == len(set(chunk_ids))
        assert any(chunk_id.endswith("#1") for chunk_id in chunk_ids)
    
    def test_chunk_preserves_source_path(self):
        chunker = StructureAwareChunker()
        text = "14A.35: Rule\n\nContent."
        chunks = chunker.chunk_document(
            document_id="doc1",
            text=text,
            source_path="data/raw/connected_transactions.md"
        )
        
        assert all(c.source_path == "data/raw/connected_transactions.md" for c in chunks)
    
    def test_save_and_load_chunks(self):
        chunker = StructureAwareChunker()
        text = "14A.35: Rule\n\nContent here."
        chunks = chunker.chunk_document(
            document_id="test-doc",
            text=text,
            source_path="test.md"
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = save_chunks(chunks, Path(tmpdir))
            
            assert output_path.exists()
            
            loaded_chunks = load_chunks(output_path)
            
            assert len(loaded_chunks) == len(chunks)
            assert loaded_chunks[0].chunk_id == chunks[0].chunk_id
            assert loaded_chunks[0].text == chunks[0].text
    
    def test_empty_text_returns_empty_chunks(self):
        chunker = StructureAwareChunker()
        chunks = chunker.chunk_document(
            document_id="empty-doc",
            text="",
            source_path="empty.md"
        )
        
        assert len(chunks) == 1
        assert chunks[0].text == ""
