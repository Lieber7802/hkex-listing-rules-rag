"""TransactionClassifierTool — Maps size-test ratio + transaction type + connected
status to a full HKEX classification with applicable rules and requirements.

Output includes: classification, chapter, primary_rule, disclosure_level,
shareholder_vote_required, ifa_required, circular_required,
announcement_deadline_days, applicable_rules, connected_override.
"""

from typing import Dict, Any, List, Optional

from app.tools.base_tool import BaseTool


# ── Tier definitions ─────────────────────────────────────────────

_TIER_RULES: Dict[str, Dict[str, Any]] = {
    "de_minimis": {
        "chapter": "Chapter 14",
        "primary_rule": "Rule 14.04",
        "disclosure_level": "minimal",
        "shareholder_vote_required": False,
        "ifa_required": False,
        "circular_required": False,
        "announcement_deadline_days": 0,
        "applicable_rules": ["14.04"],
    },
    "share_transaction": {
        "chapter": "Chapter 14",
        "primary_rule": "Rule 14.33",
        "disclosure_level": "low",
        "shareholder_vote_required": False,
        "ifa_required": False,
        "circular_required": False,
        "announcement_deadline_days": 3,
        "applicable_rules": ["14.33", "14.34"],
    },
    "discloseable_transaction": {
        "chapter": "Chapter 14",
        "primary_rule": "Rule 14.34",
        "disclosure_level": "medium",
        "shareholder_vote_required": False,
        "ifa_required": False,
        "circular_required": True,
        "announcement_deadline_days": 3,
        "applicable_rules": ["14.34", "14.35", "14.38"],
    },
    "major_transaction": {
        "chapter": "Chapter 14",
        "primary_rule": "Rule 14.52",
        "disclosure_level": "high",
        "shareholder_vote_required": True,
        "ifa_required": False,
        "circular_required": True,
        "announcement_deadline_days": 3,
        "applicable_rules": ["14.52", "14.34", "14.38A"],
    },
    "very_substantial": {
        "chapter": "Chapter 14",
        "primary_rule": "Rule 14.06(6)",
        "disclosure_level": "very_high",
        "shareholder_vote_required": True,
        "ifa_required": False,
        "circular_required": True,
        "announcement_deadline_days": 3,
        "applicable_rules": ["14.06(6)", "14.52", "14.34", "14.69"],
    },
}


class TransactionClassifierTool(BaseTool):

    @property
    def name(self) -> str:
        return "transaction_classifier"

    @property
    def description(self) -> str:
        return (
            "Classifies an HKEX transaction based on its highest size-test ratio "
            "and transaction type, returning applicable rules, disclosure level, "
            "and whether shareholder vote / IFA / circular are required. "
            "Applies Chapter 14A connected-transaction overrides when applicable."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "highest_ratio": {
                    "type": "number",
                    "description": "Highest size-test ratio (percentage)",
                },
                "transaction_type": {
                    "type": "string",
                    "description": "'acquisition' or 'disposal'",
                },
                "is_connected": {
                    "type": "boolean",
                    "description": "Whether this is a connected transaction",
                },
                "connected_party_type": {
                    "type": "string",
                    "description": "Type of connected party (e.g. 'director', 'substantial_shareholder')",
                },
            },
            "required": ["highest_ratio", "transaction_type", "is_connected"],
        }

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        errors = self.validate_inputs(inputs)
        if errors:
            return {"error": "; ".join(errors)}

        highest_ratio: float = inputs["highest_ratio"]
        transaction_type: str = inputs["transaction_type"]
        is_connected: bool = inputs["is_connected"]
        connected_party_type: Optional[str] = inputs.get("connected_party_type")

        # ── Determine classification ─────────────────────────────
        classification = self._classify(highest_ratio, transaction_type)
        tier = _TIER_RULES[classification]

        # Build mutable result from tier template
        result: Dict[str, Any] = {
            "classification": classification,
            "display_name": self._display_name(classification, transaction_type),
            "chapter": tier["chapter"],
            "primary_rule": tier["primary_rule"],
            "disclosure_level": tier["disclosure_level"],
            "shareholder_vote_required": tier["shareholder_vote_required"],
            "ifa_required": tier["ifa_required"],
            "circular_required": tier["circular_required"],
            "announcement_deadline_days": tier["announcement_deadline_days"],
            "applicable_rules": list(tier["applicable_rules"]),  # copy
            "connected_override": None,
        }

        # ── Connected transaction overrides ──────────────────────
        if is_connected:
            result["disclosure_level"] = "very_high"
            result["shareholder_vote_required"] = True
            result["ifa_required"] = True
            result["circular_required"] = True

            # Add Chapter 14A rules
            connected_rules = ["14A.35", "14A.36", "14A.46"]
            for rule in connected_rules:
                if rule not in result["applicable_rules"]:
                    result["applicable_rules"].append(rule)

            result["connected_override"] = {
                "connected_party_type": connected_party_type,
                "overrides_applied": [
                    "disclosure_level→very_high",
                    "shareholder_vote→required",
                    "ifa→required",
                    "circular→required",
                    "added_chapter_14A_rules",
                ],
            }

        return result

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def _classify(highest_ratio: float, transaction_type: str) -> str:
        is_disposal = transaction_type == "disposal"

        if highest_ratio < 5:
            return "de_minimis"
        elif highest_ratio < 25:
            return "share_transaction"
        elif highest_ratio < 50:
            return "discloseable_transaction"
        else:
            if is_disposal:
                return "very_substantial" if highest_ratio >= 75 else "major_transaction"
            else:
                return "very_substantial" if highest_ratio >= 100 else "major_transaction"

    @staticmethod
    def _display_name(classification: str, transaction_type: str) -> str:
        names = {
            "de_minimis": "De Minimis Transaction",
            "share_transaction": "Share Transaction",
            "discloseable_transaction": "Discloseable Transaction",
            "major_transaction": "Major Transaction",
            "very_substantial": "Very Substantial Acquisition/Disposal",
        }
        base = names.get(classification, classification)
        suffix = f" ({transaction_type.title()})" if classification != "de_minimis" else ""
        return f"{base}{suffix}"
