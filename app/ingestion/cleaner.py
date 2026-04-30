import re
from typing import List, Tuple, Optional
from app.core.logger import logger


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
        
        preserved = self._extract_preserved(text)
        
        for pattern in self.default_remove_patterns:
            text = re.sub(pattern, '\n', text)
        
        for pattern in self.remove_patterns:
            text = re.sub(pattern, '', text)
        
        text = self._normalize_whitespace(text)
        
        text = self._restore_preserved(text, preserved)
        
        text = text.strip()
        
        return text
    
    def _extract_preserved(self, text: str) -> List[Tuple[str, str]]:
        preserved = []
        for pattern in self.preserve_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                preserved.append((match.group(0), f"__PRESERVED_{len(preserved)}__"))
        return preserved
    
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
    
    def extract_structure_markers(self, text: str) -> List[dict]:
        markers = []
        
        for match in self.chapter_pattern.finditer(text):
            markers.append({
                'type': 'chapter',
                'number': match.group(1),
                'position': match.start(),
                'text': match.group(0)
            })
        
        for match in self.section_pattern.finditer(text):
            markers.append({
                'type': 'section',
                'number': match.group(1),
                'position': match.start(),
                'text': match.group(0)
            })
        
        for match in self.rule_number_pattern.finditer(text):
            markers.append({
                'type': 'rule',
                'number': match.group(1),
                'position': match.start(),
                'text': match.group(0)
            })
        
        markers.sort(key=lambda x: x['position'])
        
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
