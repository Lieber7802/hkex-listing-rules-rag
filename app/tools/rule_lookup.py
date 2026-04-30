"""RuleLookupTool — Retrieves rule text from IndexStore by rule number.

Uses IndexStore.get_chunks_by_rule_number for exact-match lookup.
Normalizes input: strips "Rule " prefix, trims whitespace.
Returns chunks sorted by chunk_order.
"""

import re
from typing import Dict, Any, List, Optional

from app.tools.base_tool import BaseTool
from app.retrieval.index_store import IndexStore


class RuleLookupTool(BaseTool):

    def __init__(self, index_store: Optional[IndexStore] = None):
        self._index_store = index_store

    @property
    def name(self) -> str:
        return "rule_lookup"

    @property
    def description(self) -> str:
        return (
            "Looks up the full text of an HKEX Listing Rule by its rule number "
            "(e.g. '14.52', '14A.35'). Returns all matching chunks sorted by order."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rule_number": {
                    "type": "string",
                    "description": "Rule number to look up (e.g. '14.52', 'Rule 14A.35')",
                },
            },
            "required": ["rule_number"],
        }

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        errors = self.validate_inputs(inputs)
        if errors:
            return {
                "rule_found": False,
                "chunks": [],
                "total_chunks": 0,
                "retrieval_method": "exact_match",
                "error": "; ".join(errors),
            }

        if self._index_store is None:
            return {
                "rule_found": False,
                "chunks": [],
                "total_chunks": 0,
                "retrieval_method": "exact_match",
                "error": "IndexStore not available",
            }

        raw = inputs["rule_number"]
        normalized = self._normalize(raw)

        chunks = self._index_store.get_chunks_by_rule_number(normalized)

        chunk_data = [
            {
                "chunk_id": c.chunk_id,
                "rule_number": c.rule_number,
                "section_title": c.section_title,
                "chapter": c.chapter,
                "text": c.text,
                "source_path": c.source_path,
                "chunk_order": c.chunk_order,
            }
            for c in chunks
        ]

        return {
            "rule_found": len(chunk_data) > 0,
            "chunks": chunk_data,
            "total_chunks": len(chunk_data),
            "retrieval_method": "exact_match",
        }

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def _normalize(raw: str) -> str:
        """Normalize user input to a bare rule number.

        Examples:
            'Rule 14.52'  → '14.52'
            '  14A.35  '  → '14A.35'
            'rule 14.52'  → '14.52'
        """
        text = raw.strip()
        # Strip leading "Rule " (case-insensitive)
        text = re.sub(r"^[Rr]ule\s+", "", text)
        return text.strip()
