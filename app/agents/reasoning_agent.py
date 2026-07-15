from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.schemas.document import Chunk
from app.schemas.query import PlannerOutput
from app.retrieval.hybrid_retriever import RetrievalResult
from app.core.config import settings
from app.core.llm_client import get_llm_client
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

    def _get_client(self):
        return get_llm_client()

    def reason(
        self,
        query: str,
        planner_output: PlannerOutput,
        retrieval_results: List[RetrievalResult],
        chat_history: Optional[List[Dict[str, str]]] = None,
        history_summary: Optional[str] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
    ) -> ReasoningOutput:
        has_tool_results = tool_results and any(r.get("success") for r in tool_results)

        if not retrieval_results and not has_tool_results:
            return ReasoningOutput(
                answer="I could not find relevant information to answer your question.",
                supporting_clauses=[],
                uncertainty_note="No relevant documents found in the knowledge base.",
                used_chunk_ids=[]
            )

        chunks = [r for r in retrieval_results if r.chunk is not None]
        context = ""
        if chunks:
            context = self._build_context(chunks)

        tool_context = ""
        if has_tool_results:
            tool_context = self._build_tool_context(tool_results)

        client = self._get_client()

        if client is not None and self.llm_provider in ["openai", "deepseek"]:
            try:
                answer = self._generate_with_llm(
                    client, query, context, planner_output, chat_history,
                    history_summary, tool_context,
                )
            except Exception as e:
                logger.error(f"LLM generation failed: {e}")
                if has_tool_results:
                    answer = self._generate_tool_fallback(query, tool_results)
                elif chunks:
                    answer = self._generate_fallback(query, context, chunks)
                else:
                    answer = "No relevant information found."
        elif has_tool_results:
            answer = self._generate_tool_fallback(query, tool_results)
        elif chunks:
            answer = self._generate_fallback(query, context, chunks)
        else:
            answer = "No relevant information found."

        supporting_clauses = self._extract_supporting_clauses(chunks)
        if has_tool_results:
            for r in tool_results:
                if r.get("success") and r.get("tool_name"):
                    supporting_clauses.append(f"Tool: {r['tool_name']}")
        used_chunk_ids = [r.chunk_id for r in chunks[:8]]

        uncertainty_note = None
        if len(chunks) < 3 and not has_tool_results:
            if all(r.score < 0.5 for r in chunks):
                uncertainty_note = "The available evidence may not fully address all aspects of your question. Please consult the original HKEX Listing Rules for definitive guidance."

        logger.info(f"Generated answer with {len(used_chunk_ids)} supporting chunks, tool_results={bool(has_tool_results)}")

        return ReasoningOutput(
            answer=answer,
            supporting_clauses=list(set(supporting_clauses)),
            uncertainty_note=uncertainty_note,
            used_chunk_ids=used_chunk_ids
        )
    
    def _build_context(self, results: List[RetrievalResult]) -> str:
        context_parts = []
        max_results = min(len(results), 10)
        for i, result in enumerate(results[:max_results], 1):
            chunk = result.chunk
            text = chunk.text[:800] + ("..." if len(chunk.text) > 800 else "")
            context_parts.append(
                f"[{i}] Rule {chunk.rule_number or 'N/A'} - {chunk.section_title or 'General'}\n"
                f"Source: {chunk.source_path}\n"
                f"Content: {text}\n"
            )

        return "\n".join(context_parts)

    def _build_tool_context(self, tool_results: List[Dict[str, Any]]) -> str:
        parts = []
        for r in tool_results:
            if not r.get("success"):
                parts.append(f"### {r.get('tool_name', 'Unknown Tool')} — Error\n{r.get('error', 'Unknown error')}\n")
                continue
            tool_name = r.get("tool_name", "Tool")
            output = r.get("output", {})
            if isinstance(output, dict):
                import json
                formatted = json.dumps(output, indent=2, ensure_ascii=False)
            else:
                formatted = str(output)
            parts.append(f"### {tool_name} Result\n{formatted}\n")
        return "\n".join(parts)

    def _generate_tool_fallback(self, query: str, tool_results: List[Dict[str, Any]]) -> str:
        successful = [r for r in tool_results if r.get("success")]
        if not successful:
            return "Tool execution failed. No results available."
        parts = []
        for r in successful:
            name = r.get("tool_name", "Tool")
            output = r.get("output", {})
            if isinstance(output, dict):
                if output.get("ratios"):
                    parts.append(self._format_size_test_result(output))
                elif output.get("rule_found") is not None:
                    chunks = output.get("chunks", [])
                    for c in chunks:
                        parts.append(f"**Rule {c.get('rule_number', '')}** ({c.get('section_title', '')}):\n{c.get('text', '')}")
                elif output.get("classification"):
                    parts.append(self._format_classifier_result(output))
                elif output.get("sections"):
                    parts.append(self._format_checklist_result(output))
                else:
                    import json
                    parts.append(f"{name}: {json.dumps(output, indent=2, ensure_ascii=False)}")
            else:
                parts.append(str(output))
        return "\n\n".join(parts)

    def _format_size_test_result(self, output: Dict[str, Any]) -> str:
        ratios = output.get("ratios", {})
        lines = ["**Size Test Ratios Calculated:**"]
        for name, val in ratios.items():
            label = name.replace("_", " ").replace("ratio", "Ratio").title()
            lines.append(f"- {label}: {val}%")
        if output.get("highest_ratio"):
            lines.append(f"\n**Highest ratio:** {output['highest_ratio']}% ({output.get('highest_ratio_name', '')})")
        if output.get("suggested_classification"):
            lines.append(f"**Suggested classification:** {output['suggested_classification'].replace('_', ' ').title()}")
        return "\n".join(lines)

    def _format_classifier_result(self, output: Dict[str, Any]) -> str:
        lines = [f"**Transaction Classification:** {output.get('display_name', '')}"]
        if output.get("chapter"):
            lines.append(f"- Chapter: {output['chapter']}")
        if output.get("disclosure_level"):
            lines.append(f"- Disclosure Level: {output['disclosure_level']}")
        if output.get("shareholder_vote_required") is not None:
            lines.append(f"- Shareholder Vote Required: {'Yes' if output['shareholder_vote_required'] else 'No'}")
        if output.get("ifa_required") is not None:
            lines.append(f"- IFA Required: {'Yes' if output['ifa_required'] else 'No'}")
        if output.get("circular_required") is not None:
            lines.append(f"- Circular Required: {'Yes' if output['circular_required'] else 'No'}")
        if output.get("applicable_rules"):
            lines.append(f"- Applicable Rules: {', '.join(output['applicable_rules'])}")
        return "\n".join(lines)

    def _format_checklist_result(self, output: Dict[str, Any]) -> str:
        lines = [f"**Disclosure Checklist:** {output.get('classification', '').replace('_', ' ').title()}"]
        for section in output.get("sections", []):
            lines.append(f"\n**{section.get('name', '')}**")
            for item in section.get("items", []):
                req = "Required" if item.get("required") else "Optional"
                lines.append(f"- [{req}] {item.get('task', '')} (Rule {item.get('rule_reference', '')})")
        return "\n".join(lines)
    
    def _generate_with_llm(
        self, client: Any, query: str, context: str, planner_output: PlannerOutput,
        chat_history: Optional[List[Dict[str, str]]] = None,
        history_summary: Optional[str] = None, tool_context: str = "",
    ) -> str:
        system_prompt = """You are a compliance assistant for HKEX Listing Rules.
Answer questions based ONLY on the provided context and tool results.
Always cite the specific rule numbers when making statements.
If tool results are provided, incorporate them into your answer with clear formatting.
If the context does not contain sufficient information, state that clearly.
Be concise and precise in your answers."""

        context_section = ""
        if context:
            context_section += f"Context from HKEX Listing Rules:\n{context}\n\n"
        if tool_context:
            context_section += f"Tool Results:\n{tool_context}\n\n"
        if not context_section:
            context_section = "No context or tool results available.\n\n"

        user_prompt = f"""{context_section}Question: {query}

Query type: {planner_output.query_type}

Please provide a clear, citation-grounded answer based on the context and tool results above."""

        messages = [{"role": "system", "content": system_prompt}]

        if history_summary:
            messages.append({"role": "system", "content": f"Earlier conversation context: {history_summary}"})

        if chat_history:
            messages.extend(chat_history)

        messages.append({"role": "user", "content": user_prompt})

        response = client.chat.completions.create(
            model=self.llm_model,
            messages=messages,
            max_tokens=1000,
            temperature=0.3
        )

        return response.choices[0].message.content
    
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
