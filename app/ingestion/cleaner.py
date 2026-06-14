import re
from typing import List, Tuple, Optional
from app.core.logger import logger
from app.ingestion.chunker import StructureBlock


class TextCleaner:
    def __init__(
        self,
        remove_patterns: Optional[List[str]] = None,
        preserve_patterns: Optional[List[str]] = None
    ):
        self.remove_patterns = remove_patterns or []
        self.preserve_patterns = preserve_patterns or []
        
        self.default_remove_patterns = [
            r'\r\n',
        ]
        
        self.rule_number_pattern = re.compile(
            r'(?:(?:Rule|rule)\s*)?(\d{1,3}(?:\.\d{1,3})?(?:\.\d{1,3})?(?:[A-Za-z])?)',
            re.IGNORECASE
        )
        
        self.chapter_pattern = re.compile(
            r'(?:Chapter|CHAPTER)\s+(\d{1,3}(?:[A-Za-z])?)',
            re.IGNORECASE
        )
        
        self.section_pattern = re.compile(
            r'(?:Section|SECTION)\s+(\d{1,3}(?:\.\d{1,3})?)',
            re.IGNORECASE
        )
    
    def clean(self, text: str) -> str:
        if not text:
            return ""
        
        text, preserved = self._extract_preserve(text)
        
        for pattern in self.default_remove_patterns:
            text = re.sub(pattern, '\n', text)
        
        for pattern in self.remove_patterns:
            text = re.sub(pattern, '', text)
        
        text = self._normalize_whitespace(text)
        
        text = self._restore_preserved(text, preserved)
        
        text = text.strip()
        
        return text
    
    def _extract_preserve(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
        preserved: List[Tuple[str, str]] = []
        for pattern in self.preserve_patterns:
            def _replace(match, p=preserved):
                original = match.group(0)
                placeholder = f"__PRESERVED_{len(p)}__"
                p.append((original, placeholder))
                return placeholder
            text = re.sub(pattern, _replace, text)
        return text, preserved
    
    def _restore_preserved(self, text: str, preserved: List[Tuple[str, str]]) -> str:
        for original, placeholder in preserved:
            text = text.replace(placeholder, original)
        return text
    
    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'\n[ \t]+', '\n', text)
        text = re.sub(r'[ \t]+\n', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text
    
    def extract_structure_markers(self, text: str) -> List[StructureBlock]:
        markers: List[StructureBlock] = []

        for match in self.chapter_pattern.finditer(text):
            markers.append(StructureBlock(
                block_type='chapter',
                number=match.group(1),
                title=None,
                start_pos=match.start(),
                end_pos=match.end(),
                text=match.group(0),
                parent_chapter=None,
                parent_section=None,
            ))

        for match in self.section_pattern.finditer(text):
            markers.append(StructureBlock(
                block_type='section',
                number=match.group(1),
                title=None,
                start_pos=match.start(),
                end_pos=match.end(),
                text=match.group(0),
                parent_chapter=None,
                parent_section=None,
            ))

        for match in self.rule_number_pattern.finditer(text):
            markers.append(StructureBlock(
                block_type='rule',
                number=match.group(1),
                title=None,
                start_pos=match.start(),
                end_pos=match.end(),
                text=match.group(0),
                parent_chapter=None,
                parent_section=None,
            ))

        markers.sort(key=lambda x: x.start_pos)

        return markers


def clean_document_text(text: str, preserve_rule_numbers: bool = True) -> str:
    cleaner = TextCleaner()
    
    if preserve_rule_numbers:
        cleaner.preserve_patterns = [
            r'(?:(?:Rule|rule)\s*)?\d{1,3}(?:\.\d{1,3})?(?:\.\d{1,3})?(?:[A-Za-z])?',
            r'(?:Chapter|CHAPTER)\s+\d{1,3}(?:[A-Za-z])?',
            r'(?:Section|SECTION)\s+\d{1,3}(?:\.\d{1,3})?',
        ]
    
    return cleaner.clean(text)
