"""SizeTestCalculatorTool — Calculates HKEX five size-test ratios and suggests
transaction classification per Chapter 14 of the Main Board Listing Rules.

Five ratios (each = acquired/issuer × 100):
  consideration_ratio, assets_ratio, profits_ratio, shares_ratio, net_assets_ratio

Classification by HIGHEST ratio + transaction_type:
  <5%      → de_minimis
  5-25%    → share_transaction
  25-50%   → discloseable_transaction
  50-100%  (acq) / 50-75% (disp) → major_transaction
  ≥100%    (acq) / ≥75%  (disp)  → very_substantial
"""

from typing import Dict, Any, List

from app.tools.base_tool import BaseTool


class SizeTestCalculatorTool(BaseTool):

    @property
    def name(self) -> str:
        return "size_test_calculator"

    @property
    def description(self) -> str:
        return (
            "Calculates the five HKEX size-test ratios (consideration, assets, "
            "profits, shares, net assets) and suggests a transaction classification "
            "(de minimis, share transaction, discloseable, major, very substantial) "
            "based on the highest ratio and transaction type (acquisition/disposal)."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "issuer_market_cap": {"type": "number", "description": "Issuer market capitalisation (HK$ millions)"},
                "issuer_total_assets": {"type": "number", "description": "Issuer total assets (HK$ millions)"},
                "issuer_net_assets": {"type": "number", "description": "Issuer net assets (HK$ millions)"},
                "issuer_annual_profit": {"type": "number", "description": "Issuer annual profit (HK$ millions)"},
                "issuer_shares_outstanding": {"type": "number", "description": "Issuer shares outstanding"},
                "transaction_consideration": {"type": "number", "description": "Transaction consideration (HK$ millions)"},
                "acquired_assets": {"type": "number", "description": "Acquired entity total assets (HK$ millions)"},
                "acquired_profit": {"type": "number", "description": "Acquired entity annual profit (HK$ millions)"},
                "acquired_net_assets": {"type": "number", "description": "Acquired entity net assets (HK$ millions)"},
                "consideration_shares": {"type": "number", "description": "Number of consideration shares issued (default 0)"},
                "transaction_type": {"type": "string", "description": "Transaction type: 'acquisition' or 'disposal'"},
            },
            "required": [
                "transaction_consideration",
                "transaction_type",
            ],
        }

    # ── public entry point ───────────────────────────────────────

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        errors = self.validate_inputs(inputs)
        if errors:
            return {"error": "; ".join(errors), "ratios": {}, "warnings": []}

        warnings: List[str] = []

        # Extract values with defaults for non-required fields
        issuer_market_cap = inputs.get("issuer_market_cap", 0) or 0
        issuer_total_assets = inputs.get("issuer_total_assets", 0) or 0
        issuer_net_assets = inputs.get("issuer_net_assets", 0) or 0
        issuer_annual_profit = inputs.get("issuer_annual_profit", 0) or 0
        issuer_shares_outstanding = inputs.get("issuer_shares_outstanding", 0) or 0
        transaction_consideration = inputs["transaction_consideration"]
        acquired_assets = inputs.get("acquired_assets", 0) or 0
        acquired_profit = inputs.get("acquired_profit", 0) or 0
        acquired_net_assets = inputs.get("acquired_net_assets", 0) or 0
        consideration_shares = inputs.get("consideration_shares", 0) or 0
        transaction_type = inputs["transaction_type"]

        # ── Zero-denominator guard ───────────────────────────────
        unavailable = []
        ratios: Dict[str, float] = {}
        if issuer_market_cap:
            ratios["consideration_ratio"] = round(transaction_consideration / issuer_market_cap * 100, 1)
        else:
            unavailable.append("consideration_ratio (issuer_market_cap missing or zero)")
        if issuer_total_assets:
            ratios["assets_ratio"] = round(acquired_assets / issuer_total_assets * 100, 1)
        else:
            unavailable.append("assets_ratio (issuer_total_assets missing or zero)")
        if issuer_net_assets:
            ratios["net_assets_ratio"] = round(acquired_net_assets / issuer_net_assets * 100, 1)
        else:
            unavailable.append("net_assets_ratio (issuer_net_assets missing or zero)")

        # ── Negative profit handling ─────────────────────────────
        profit_numerator = acquired_profit
        profit_denominator = issuer_annual_profit

        if profit_denominator and (profit_numerator < 0 or profit_denominator < 0):
            warnings.append(
                "Negative profit detected — using absolute values for profits ratio calculation."
            )
            profit_numerator = abs(profit_numerator)
            profit_denominator = abs(profit_denominator)

        # ── Compute ratios ───────────────────────────────────────
        if profit_denominator:
            ratios["profits_ratio"] = round(profit_numerator / profit_denominator * 100, 1)
        else:
            unavailable.append("profits_ratio (issuer_annual_profit missing or zero)")
        if consideration_shares == 0:
            ratios["shares_ratio"] = 0.0
        elif issuer_shares_outstanding:
            ratios["shares_ratio"] = round(consideration_shares / issuer_shares_outstanding * 100, 1)
        else:
            unavailable.append("shares_ratio (issuer_shares_outstanding missing or zero)")

        if unavailable:
            warnings.append("Unavailable ratios: " + "; ".join(unavailable))
        if not ratios:
            return {"error": "No size-test ratios can be computed from the supplied inputs.", "ratios": {}, "warnings": warnings}

        # ── Highest ratio ────────────────────────────────────────
        highest_name = max(ratios, key=ratios.get)  # type: ignore[arg-type]
        highest_value = ratios[highest_name]

        # ── Classification ───────────────────────────────────────
        classification = self._classify(highest_value, transaction_type)

        # ── Very-high-ratio warning ──────────────────────────────
        if highest_value > 500:
            warnings.append(
                f"Unusually high ratio ({highest_value}% > 500%). "
                "Please verify the input figures."
            )

        return {
            "ratios": ratios,
            "highest_ratio": highest_value,
            "highest_ratio_name": highest_name,
            "suggested_classification": classification,
            "warnings": warnings,
            "partial_result": bool(unavailable),
        }

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def _classify(highest_ratio: float, transaction_type: str) -> str:
        """Map highest ratio + transaction type to classification label."""
        is_disposal = transaction_type == "disposal"

        if highest_ratio < 5:
            return "de_minimis"
        elif highest_ratio < 25:
            return "share_transaction"
        elif highest_ratio < 50:
            return "discloseable_transaction"
        else:
            # For disposal: major up to 75%, very_substantial ≥ 75%
            # For acquisition: major up to 100%, very_substantial ≥ 100%
            if is_disposal:
                if highest_ratio < 75:
                    return "major_transaction"
                else:
                    return "very_substantial"
            else:
                if highest_ratio < 100:
                    return "major_transaction"
                else:
                    return "very_substantial"
