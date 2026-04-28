from typing import List, Optional
from app.schemas.citation import Citation
from app.retrieval.hybrid_retriever import RetrievalResult
from app.core.logger import logger


class CitationFormatter:
    def __init__(self, max_snippet_length: int = 200):
        self.max_snippet_length = max_snippet_length
    
    def format_citations(self, results: List[RetrievalResult]) -> List[Citation]:
        citations = []
        
        for result in results:
            snippet = self._truncate_snippet(result.chunk.text)
            
            citation = Citation(
                chunk_id=result.chunk.chunk_id,
                document_id=result.chunk.document_id,
                rule_number=result.chunk.rule_number,
                section_title=result.chunk.section_title,
                chapter=result.chunk.chapter,
                source_path=result.chunk.source_path,
                snippet=snippet,
                score=result.score
            )
            citations.append(citation)
        
        logger.info(f"Formatted {len(citations)} citations")
        return citations
    
    def _truncate_snippet(self, text: str) -> str:
        if len(text) <= self.max_snippet_length:
            return text
        
        truncated = text[:self.max_snippet_length]
        
        last_space = truncated.rfind(' ')
        if last_space > self.max_snippet_length * 0.8:
            truncated = truncated[:last_space]
        
        return truncated + "..."


def format_citations_from_results(results: List[RetrievalResult]) -> List[Citation]:
    formatter = CitationFormatter()
    return formatter.format_citations(results)
