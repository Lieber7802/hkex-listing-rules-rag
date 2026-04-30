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
                "issuer_market_cap",
                "issuer_total_assets",
                "issuer_net_assets",
                "issuer_annual_profit",
                "issuer_shares_outstanding",
                "transaction_consideration",
                "acquired_assets",
                "acquired_profit",
                "acquired_net_assets",
                "transaction_type",
            ],
        }

    # ── public entry point ───────────────────────────────────────

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        errors = self.validate_inputs(inputs)
        if errors:
            return {"error": "; ".join(errors), "ratios": {}, "warnings": []}

        warnings: List[str] = []

        # Extract values
        issuer_market_cap = inputs["issuer_market_cap"]
        issuer_total_assets = inputs["issuer_total_assets"]
        issuer_net_assets = inputs["issuer_net_assets"]
        issuer_annual_profit = inputs["issuer_annual_profit"]
        issuer_shares_outstanding = inputs["issuer_shares_outstanding"]
        transaction_consideration = inputs["transaction_consideration"]
        acquired_assets = inputs["acquired_assets"]
        acquired_profit = inputs["acquired_profit"]
        acquired_net_assets = inputs["acquired_net_assets"]
        consideration_shares = inputs.get("consideration_shares", 0)
        transaction_type = inputs["transaction_type"]

        # ── Zero-denominator guard ───────────────────────────────
        zero_fields = []
        if issuer_market_cap == 0:
            zero_fields.append("issuer_market_cap")
        if issuer_total_assets == 0:
            zero_fields.append("issuer_total_assets")
        if issuer_net_assets == 0:
            zero_fields.append("issuer_net_assets")
        if issuer_annual_profit == 0:
            zero_fields.append("issuer_annual_profit")
        if issuer_shares_outstanding == 0 and consideration_shares != 0:
            zero_fields.append("issuer_shares_outstanding")

        if zero_fields:
            return {
                "error": f"Zero value(s) in denominator field(s): {', '.join(zero_fields)}. Cannot compute ratio.",
                "ratios": {},
                "warnings": [],
            }

        # ── Negative profit handling ─────────────────────────────
        profit_numerator = acquired_profit
        profit_denominator = issuer_annual_profit

        if profit_numerator < 0 or profit_denominator < 0:
            warnings.append(
                "Negative profit detected — using absolute values for profits ratio calculation."
            )
            profit_numerator = abs(profit_numerator)
            profit_denominator = abs(profit_denominator)

        # ── Compute ratios ───────────────────────────────────────
        consideration_ratio = round(transaction_consideration / issuer_market_cap * 100, 1)
        assets_ratio = round(acquired_assets / issuer_total_assets * 100, 1)
        profits_ratio = round(profit_numerator / profit_denominator * 100, 1)
        net_assets_ratio = round(acquired_net_assets / issuer_net_assets * 100, 1)

        if consideration_shares == 0:
            shares_ratio = 0.0
        else:
            shares_ratio = round(consideration_shares / issuer_shares_outstanding * 100, 1)

        ratios = {
            "consideration_ratio": consideration_ratio,
            "assets_ratio": assets_ratio,
            "profits_ratio": profits_ratio,
            "shares_ratio": shares_ratio,
            "net_assets_ratio": net_assets_ratio,
        }

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
