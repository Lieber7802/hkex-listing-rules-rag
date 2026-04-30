import pytest
from app.ingestion.cleaner import TextCleaner, clean_document_text


class TestTextCleaner:
    
    def test_removes_excessive_newlines(self):
        cleaner = TextCleaner()
        text = "Line 1\n\n\n\n\nLine 2"
        result = cleaner.clean(text)
        assert result == "Line 1\n\nLine 2"
    
    def test_removes_excessive_spaces(self):
        cleaner = TextCleaner()
        text = "Word1     Word2"
        result = cleaner.clean(text)
        assert result == "Word1 Word2"
    
    def test_normalizes_crlf(self):
        cleaner = TextCleaner()
        text = "Line 1\r\nLine 2"
        result = cleaner.clean(text)
        assert "\r\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result
    
    def test_preserves_rule_numbers(self):
        cleaner = TextCleaner()
        cleaner.preserve_patterns = [
            r'(?:(?:Rule|rule)\s*)?\d{1,3}(?:\.\d{1,3})?(?:\.\d{1,3})?(?:[A-Za-z])?'
        ]
        text = "According to Rule 14A.35, the requirements are..."
        result = cleaner.clean(text)
        assert "14A.35" in result
    
    def test_preserves_chapter_markers(self):
        cleaner = TextCleaner()
        text = "Chapter 14A deals with connected transactions."
        result = cleaner.clean(text)
        assert "Chapter 14A" in result
    
    def test_extract_structure_markers_finds_chapters(self):
        cleaner = TextCleaner()
        text = "Chapter 14\nSome content\nChapter 14A\nMore content"
        markers = cleaner.extract_structure_markers(text)
        chapter_markers = [m for m in markers if m['type'] == 'chapter']
        assert len(chapter_markers) == 2
        assert chapter_markers[0]['number'] == '14'
        assert chapter_markers[1]['number'] == '14A'
    
    def test_extract_structure_markers_finds_rules(self):
        cleaner = TextCleaner()
        text = "Rule 14.26 states...\n14A.35 requires..."
        markers = cleaner.extract_structure_markers(text)
        rule_markers = [m for m in markers if m['type'] == 'rule']
        assert len(rule_markers) >= 2
    
    def test_clean_document_text_preserves_numbering(self):
        text = "Rule  14A.35   requires   disclosure.\n\n\n\nSee also Rule 14.26."
        result = clean_document_text(text, preserve_rule_numbers=True)
        assert "14A.35" in result
        assert "14.26" in result
        assert "\n\n\n\n" not in result
    
    def test_empty_text_returns_empty(self):
        cleaner = TextCleaner()
        result = cleaner.clean("")
        assert result == ""
    
    def test_whitespace_only_returns_empty(self):
        cleaner = TextCleaner()
        result = cleaner.clean("   \n\n   \t\t  ")
        assert result == ""
