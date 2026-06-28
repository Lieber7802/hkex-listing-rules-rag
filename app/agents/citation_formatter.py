from typing import List

from app.schemas.citation import Citation
from app.retrieval.hybrid_retriever import RetrievalResult
from app.core.logger import logger

DEFAULT_MAX_SNIPPET_LENGTH = 200


def format_citations(
    results: List[RetrievalResult],
    max_snippet_length: int = DEFAULT_MAX_SNIPPET_LENGTH,
) -> List[Citation]:
    citations = []
    for result in results:
        snippet = _truncate_snippet(result.chunk.text, max_snippet_length)
        citation = Citation(
            chunk_id=result.chunk.chunk_id,
            document_id=result.chunk.document_id,
            rule_number=result.chunk.rule_number,
            section_title=result.chunk.section_title,
            chapter=result.chunk.chapter,
            source_path=result.chunk.source_path,
            snippet=snippet,
            score=result.score,
        )
        citations.append(citation)
    logger.info(f"Formatted {len(citations)} citations")
    return citations


def _truncate_snippet(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_space = truncated.rfind(" ")
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]
    return truncated + "..."


class CitationFormatter:
    def __init__(self, max_snippet_length: int = DEFAULT_MAX_SNIPPET_LENGTH):
        self.max_snippet_length = max_snippet_length

    def format_citations(self, results: List[RetrievalResult]) -> List[Citation]:
        return format_citations(results, max_snippet_length=self.max_snippet_length)


format_citations_from_results = format_citations
