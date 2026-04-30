from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import os

from app.schemas.document import Chunk
from app.schemas.query import PlannerOutput
from app.retrieval.hybrid_retriever import RetrievalResult
from app.core.config import settings
from app.core.logger import logger


@dataclass
class ReasoningOutput:
    answer: str
    supporting_clauses: List[str]
    uncertainty_note: Optional[str]
    used_chunk_ids: List[str]


class ReasoningAgent:
    def __init__(self, llm_provider: Optional[str] = None, llm_model: Optional[str] = None):
        self.llm_provider = llm_provider or settings.llm_provider
        self.llm_model = llm_model or settings.llm_model
        self._client = None
    
    def _get_client(self):
        if self._client is not None:
            return self._client
        
        if self.llm_provider in ["openai", "deepseek"]:
            try:
                from openai import OpenAI
                api_key = settings.llm_api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
                if api_key:
                    self._client = OpenAI(api_key=api_key, base_url=settings.llm_base_url)
                    logger.info(f"Initialized LLM client for {self.llm_provider}: {self.llm_model}")
                else:
                    logger.warning("LLM API key not found. Using fallback reasoning.")
            except ImportError:
                logger.warning("openai package not installed. Using fallback reasoning.")
        
        return self._client
    
    def reason(
        self,
        query: str,
        planner_output: PlannerOutput,
        retrieval_results: List[RetrievalResult]
    ) -> ReasoningOutput:
        if not retrieval_results:
            return ReasoningOutput(
                answer="I could not find relevant information to answer your question.",
                supporting_clauses=[],
                uncertainty_note="No relevant documents found in the knowledge base.",
                used_chunk_ids=[]
            )
        
        context = self._build_context(retrieval_results)
        
        client = self._get_client()
        
        if client is not None and self.llm_provider in ["openai", "deepseek"]:
            answer = self._generate_with_llm(query, context, planner_output)
        else:
            answer = self._generate_fallback(query, context, retrieval_results)
        
        supporting_clauses = self._extract_supporting_clauses(retrieval_results)
        used_chunk_ids = [r.chunk_id for r in retrieval_results[:5]]
        
        uncertainty_note = None
        if len(retrieval_results) < 3 or all(r.score < 0.5 for r in retrieval_results):
            uncertainty_note = "The available evidence may not fully address all aspects of your question. Please consult the original HKEX Listing Rules for definitive guidance."
        
        logger.info(f"Generated answer with {len(used_chunk_ids)} supporting chunks")
        
        return ReasoningOutput(
            answer=answer,
            supporting_clauses=supporting_clauses,
            uncertainty_note=uncertainty_note,
            used_chunk_ids=used_chunk_ids
        )
    
    def _build_context(self, results: List[RetrievalResult]) -> str:
        context_parts = []
        
        for i, result in enumerate(results[:10], 1):
            chunk = result.chunk
            context_parts.append(
                f"[{i}] Rule {chunk.rule_number or 'N/A'} - {chunk.section_title or 'General'}\n"
                f"Source: {chunk.source_path}\n"
                f"Content: {chunk.text[:500]}...\n"
            )
        
        return "\n".join(context_parts)
    
    def _generate_with_llm(self, query: str, context: str, planner_output: PlannerOutput) -> str:
        try:
            system_prompt = """You are a compliance assistant for HKEX Listing Rules. 
Answer questions based ONLY on the provided context.
Always cite the specific rule numbers when making statements.
If the context does not contain sufficient information, state that clearly.
Be concise and precise in your answers."""

            user_prompt = f"""Context from HKEX Listing Rules:
{context}

Question: {query}

Query type: {planner_output.query_type}

Please provide a clear, citation-grounded answer based on the context above."""

            response = self._client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._generate_fallback(query, context, [])
    
    def _generate_fallback(
        self,
        query: str,
        context: str,
        results: List[RetrievalResult]
    ) -> str:
        if not results:
            return "No relevant information found."
        
        top_result = results[0]
        chunk = top_result.chunk
        
        answer_parts = [
            f"Based on {chunk.section_title or 'the relevant rules'}",
        ]
        
        if chunk.rule_number:
            answer_parts.append(f"(Rule {chunk.rule_number})")
        
        answer_parts.append("the following applies:")
        answer_parts.append(chunk.text[:300])
        
        if len(results) > 1:
            answer_parts.append(f"\n\nAdditional relevant information is available from {len(results) - 1} other source(s).")
        
        return " ".join(answer_parts)
    
    def _extract_supporting_clauses(self, results: List[RetrievalResult]) -> List[str]:
        clauses = []
        
        for result in results[:5]:
            if result.chunk.rule_number:
                clauses.append(f"Rule {result.chunk.rule_number}")
            elif result.chunk.section_title:
                clauses.append(result.chunk.section_title)
        
        return list(set(clauses))


def reason_with_evidence(
    query: str,
    planner_output: PlannerOutput,
    retrieval_results: List[RetrievalResult]
) -> ReasoningOutput:
    agent = ReasoningAgent()
    return agent.reason(query, planner_output, retrieval_results)
