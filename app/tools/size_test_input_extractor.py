"""SizeTestInputExtractor — Heuristic extraction of size_test_calculator inputs
from natural language queries.

Uses keyword-to-field association with QueryParser helpers to extract:
  10 required + 1 optional fields for size_test_calculator.

LLM is preferred for extraction; this heuristic is the fallback.
"""

from typing import Dict, Any, List, Optional, Tuple
import re


class SizeTestInputExtractor:
    FIELD_KEYWORDS = {
        "issuer_market_cap": [
            r"market\s*cap(?:itali[sz]ation)?", r"market\s*value",
            r"\u5e02\u503c", r"\u5e02\u573a\u4f30\u503c",
        ],
        "issuer_total_assets": [
            r"total\s*assets", r"\u603b\u8d44\u4ea7",
        ],
        "issuer_net_assets": [
            r"net\s*assets", r"NAV", r"\u51c0\u8d44\u4ea7",
        ],
        "issuer_annual_profit": [
            r"(?:annual\s+)?profit(?:\s+after\s+tax)?", r"PAT",
            r"\u5e74\u5ea6?\u6ea2\u5229", r"\u5229\u6da6", r"\u7d14\u5229",
        ],
        "issuer_shares_outstanding": [
            r"(?:shares?\s*)?outstanding", r"issued\s*shares",
            r"\u5df2\u767c\u884c\u80a1\u4efd", r"\u767c\u884c\u5728\u5916",
        ],
        "transaction_consideration": [
            r"consideration", r"transaction\s*(?:price|value|amount)",
            r"\u4ea4\u6613\u4ee3\u50f9", r"\u4ee3\u50f9", r"\u4ea4\u6613\u91d1\u984d",
        ],
        "acquired_assets": [
            r"acquired\s+assets", r"target\s+assets",
            r"\u88ab\u6536\u8cfc\u8cc7\u7522", r"\u6536\u8cfc\u8cc7\u7522", r"\u76ee\u6a19\u8cc7\u7522",
        ],
        "acquired_profit": [
            r"acquired\s+profit", r"target\s+profit",
            r"\u88ab\u6536\u8cfc\u6ea2\u5229", r"\u76ee\u6a19\u5229\u6da6",
        ],
        "acquired_net_assets": [
            r"acquired\s+net\s+assets", r"target\s+NAV",
            r"\u88ab\u6536\u8cfc\u51c0\u8cc7\u7522", r"\u76ee\u6a19\u51c0\u8cc7\u7522",
        ],
    }

    CURRENCY_SCALE = {"\u4ebf": 1e8, "\u4e07": 1e4, "\u767e\u4e07": 1e6,
                      "million": 1e6, "billion": 1e9, "m": 1e6, "bn": 1e9}

    def __init__(self):
        from app.tools.query_parser import QueryParser
        self.parser = QueryParser

    REQUIRED_FIELDS = {"transaction_consideration", "transaction_type"}

    def extract(self, query: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if not query:
            result["_confidence"] = 0.0
            result["_missing"] = list(self.REQUIRED_FIELDS) + list(self.FIELD_KEYWORDS.keys())
            return result

        tx_type = self.parser.extract_transaction_type(query)
        if tx_type:
            result["transaction_type"] = tx_type

        numbers = self._extract_all_numbers(query)

        for field_name, keywords in self.FIELD_KEYWORDS.items():
            best_match = self._find_best_number(query, keywords, numbers)
            if best_match is not None:
                result[field_name] = best_match

        result["_confidence"] = self._compute_confidence(result)
        result["_missing"] = self._compute_missing(result)

        return result

    def get_confidence(self, result: Dict[str, Any]) -> float:
        return result.get("_confidence", 0.0)

    # ── helpers ───────────────────────────────────────────────────

    def _extract_all_numbers(self, query: str) -> List[Tuple[float, int, int]]:
        """Extract all numbers with their positions. Returns [(value, start, end)]."""
        results = []
        pattern = r'(?:HK\$|HKD|USD|US\$|RMB|CNY)?\s*(\d+(?:[.,]\d+)?)\s*(?:\u4ebf|\u4e07|\u767e\u4e07|million|billion|m|bn|k|thousand)?\s*(?:HK\$|HKD|USD|US\$|RMB|CNY)?'
        for m in re.finditer(pattern, query, re.IGNORECASE):
            num_str = m.group(1)
            if num_str:
                try:
                    val = float(num_str.replace(",", "").replace(" ", ""))
                    # Apply scale from surrounding context
                    scale_text = m.group(0)
                    for scale_str, factor in self.CURRENCY_SCALE.items():
                        if scale_str in scale_text.lower():
                            val *= factor
                            break
                    results.append((val, m.start(), m.end()))
                except ValueError:
                    continue
        return results

    def _find_best_number(self, query: str, keywords: List[str],
                          numbers: List[Tuple[float, int, int]]) -> Optional[float]:
        candidate: Optional[Tuple[float, float]] = None

        for kw in keywords:
            for m in re.finditer(kw, query, re.IGNORECASE):
                kw_pos = m.start()

                for val, num_start, _num_end in numbers:
                    distance = abs(num_start - kw_pos)
                    if distance <= 80:
                        score = 1.0 / (1.0 + distance * 0.02)
                        if candidate is None or score > candidate[1]:
                            candidate = (val, score)

        return candidate[0] if candidate else None

    def _compute_confidence(self, result: Dict[str, Any]) -> float:
        req_filled = sum(1 for k in self.REQUIRED_FIELDS if k in result)
        req_total = len(self.REQUIRED_FIELDS)
        opt_filled = sum(1 for k in self.FIELD_KEYWORDS if k in result and k not in self.REQUIRED_FIELDS)
        opt_total = len(self.FIELD_KEYWORDS) - len(self.REQUIRED_FIELDS)

        req_score = req_filled / req_total if req_total > 0 else 0.0
        opt_score = opt_filled / opt_total if opt_total > 0 else 0.0
        return round(req_score * 0.7 + opt_score * 0.3, 2)

    def _compute_missing(self, result: Dict[str, Any]) -> List[str]:
        required = list(self.REQUIRED_FIELDS) + list(self.FIELD_KEYWORDS.keys())
        return [k for k in required if k not in result]
