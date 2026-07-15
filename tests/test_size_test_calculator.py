"""Tests for SizeTestCalculatorTool (Sprint 2).

HKEX Five Size Test Ratios:
  consideration, assets, profits, shares, net_assets

Classification by HIGHEST ratio + transaction_type:
  <5%      → de_minimis
  5-25%    → share_transaction
  25-50%   → discloseable_transaction
  50-100%  (acq) / 50-75% (disp) → major_transaction
  ≥100%    (acq) / ≥75%  (disp)  → very_substantial
"""

import pytest
from app.tools.size_test_calculator import SizeTestCalculatorTool


@pytest.fixture
def tool():
    return SizeTestCalculatorTool()


# ── Basic interface ──────────────────────────────────────────────

class TestSizeTestInterface:

    def test_name(self, tool):
        assert tool.name == "size_test_calculator"

    def test_description_non_empty(self, tool):
        assert len(tool.description) > 10

    def test_input_schema_has_required(self, tool):
        schema = tool.input_schema
        assert "properties" in schema
        assert "required" in schema
        assert "transaction_consideration" in schema["required"]


# ── Ratio computation ────────────────────────────────────────────

class TestRatioComputation:

    def test_known_ratios(self, tool):
        """Verify each ratio = (acquired / issuer) × 100, rounded 1dp."""
        result = tool.run({
            "issuer_market_cap": 1000,
            "issuer_total_assets": 2000,
            "issuer_net_assets": 500,
            "issuer_annual_profit": 100,
            "issuer_shares_outstanding": 10000,
            "transaction_consideration": 250,
            "acquired_assets": 600,
            "acquired_profit": 60,
            "acquired_net_assets": 150,
            "consideration_shares": 2000,
            "transaction_type": "acquisition",
        })

        ratios = result["ratios"]
        assert ratios["consideration_ratio"] == 25.0   # 250/1000 * 100
        assert ratios["assets_ratio"] == 30.0           # 600/2000 * 100
        assert ratios["profits_ratio"] == 60.0          # 60/100 * 100
        assert ratios["shares_ratio"] == 20.0           # 2000/10000 * 100
        assert ratios["net_assets_ratio"] == 30.0       # 150/500 * 100

    def test_cash_only_shares_ratio_zero(self, tool):
        """When consideration_shares == 0, shares_ratio should be 0."""
        result = tool.run({
            "issuer_market_cap": 1000,
            "issuer_total_assets": 2000,
            "issuer_net_assets": 500,
            "issuer_annual_profit": 100,
            "issuer_shares_outstanding": 10000,
            "transaction_consideration": 250,
            "acquired_assets": 600,
            "acquired_profit": 60,
            "acquired_net_assets": 150,
            "consideration_shares": 0,
            "transaction_type": "acquisition",
        })

        assert result["ratios"]["shares_ratio"] == 0.0

    def test_default_consideration_shares_zero(self, tool):
        """consideration_shares defaults to 0 if omitted."""
        result = tool.run({
            "issuer_market_cap": 1000,
            "issuer_total_assets": 2000,
            "issuer_net_assets": 500,
            "issuer_annual_profit": 100,
            "issuer_shares_outstanding": 10000,
            "transaction_consideration": 250,
            "acquired_assets": 600,
            "acquired_profit": 60,
            "acquired_net_assets": 150,
            "transaction_type": "acquisition",
        })

        assert result["ratios"]["shares_ratio"] == 0.0


# ── Classification thresholds (acquisition) ──────────────────────

class TestAcquisitionClassification:

    def _run(self, tool, highest_pct):
        """Helper: set consideration so that consideration_ratio = highest_pct."""
        return tool.run({
            "issuer_market_cap": 1000,
            "issuer_total_assets": 100000,
            "issuer_net_assets": 100000,
            "issuer_annual_profit": 100000,
            "issuer_shares_outstanding": 100000,
            "transaction_consideration": highest_pct * 10,  # /1000 * 100 = highest_pct
            "acquired_assets": 1,
            "acquired_profit": 1,
            "acquired_net_assets": 1,
            "consideration_shares": 0,
            "transaction_type": "acquisition",
        })

    def test_de_minimis_below_5(self, tool):
        result = self._run(tool, 4.9)
        assert result["suggested_classification"] == "de_minimis"

    def test_share_transaction_at_5(self, tool):
        result = self._run(tool, 5.0)
        assert result["suggested_classification"] == "share_transaction"

    def test_share_transaction_below_25(self, tool):
        result = self._run(tool, 24.9)
        assert result["suggested_classification"] == "share_transaction"

    def test_discloseable_at_25(self, tool):
        result = self._run(tool, 25.0)
        assert result["suggested_classification"] == "discloseable_transaction"

    def test_discloseable_below_50(self, tool):
        result = self._run(tool, 49.9)
        assert result["suggested_classification"] == "discloseable_transaction"

    def test_major_at_50(self, tool):
        result = self._run(tool, 50.0)
        assert result["suggested_classification"] == "major_transaction"

    def test_major_below_100(self, tool):
        result = self._run(tool, 99.9)
        assert result["suggested_classification"] == "major_transaction"

    def test_very_substantial_at_100(self, tool):
        result = self._run(tool, 100.0)
        assert result["suggested_classification"] == "very_substantial"

    def test_highest_ratio_tracked(self, tool):
        result = self._run(tool, 60.0)
        assert result["highest_ratio"] == 60.0
        assert result["highest_ratio_name"] == "consideration_ratio"


# ── Disposal thresholds ──────────────────────────────────────────

class TestDisposalClassification:

    def _run(self, tool, highest_pct):
        return tool.run({
            "issuer_market_cap": 1000,
            "issuer_total_assets": 100000,
            "issuer_net_assets": 100000,
            "issuer_annual_profit": 100000,
            "issuer_shares_outstanding": 100000,
            "transaction_consideration": highest_pct * 10,
            "acquired_assets": 1,
            "acquired_profit": 1,
            "acquired_net_assets": 1,
            "consideration_shares": 0,
            "transaction_type": "disposal",
        })

    def test_disposal_major_below_75(self, tool):
        result = self._run(tool, 74.9)
        assert result["suggested_classification"] == "major_transaction"

    def test_disposal_very_substantial_at_75(self, tool):
        result = self._run(tool, 75.0)
        assert result["suggested_classification"] == "very_substantial"


# ── Edge cases ───────────────────────────────────────────────────

class TestEdgeCases:

    def test_negative_profit_uses_abs_and_warns(self, tool):
        """Negative profit → use abs value, add a warning."""
        result = tool.run({
            "issuer_market_cap": 1000,
            "issuer_total_assets": 2000,
            "issuer_net_assets": 500,
            "issuer_annual_profit": -100,
            "issuer_shares_outstanding": 10000,
            "transaction_consideration": 250,
            "acquired_assets": 600,
            "acquired_profit": -60,
            "acquired_net_assets": 150,
            "consideration_shares": 0,
            "transaction_type": "acquisition",
        })

        # abs(-60) / abs(-100) * 100 = 60.0
        assert result["ratios"]["profits_ratio"] == 60.0
        assert any("negative" in w.lower() or "profit" in w.lower() for w in result["warnings"])

    def test_zero_denominator_returns_partial_result(self, tool):
        """Zero issuer denominator → validation error (not a crash)."""
        result = tool.run({
            "issuer_market_cap": 0,
            "issuer_total_assets": 2000,
            "issuer_net_assets": 500,
            "issuer_annual_profit": 100,
            "issuer_shares_outstanding": 10000,
            "transaction_consideration": 250,
            "acquired_assets": 600,
            "acquired_profit": 60,
            "acquired_net_assets": 150,
            "consideration_shares": 0,
            "transaction_type": "acquisition",
        })

        assert result.get("error") is None
        assert result["partial_result"] is True
        assert "consideration_ratio" not in result["ratios"]
        assert result["ratios"]["assets_ratio"] == 30.0

    def test_very_high_ratio_adds_warning(self, tool):
        """Ratio > 500% should trigger a warning."""
        result = tool.run({
            "issuer_market_cap": 100,
            "issuer_total_assets": 100000,
            "issuer_net_assets": 100000,
            "issuer_annual_profit": 100000,
            "issuer_shares_outstanding": 100000,
            "transaction_consideration": 600,
            "acquired_assets": 1,
            "acquired_profit": 1,
            "acquired_net_assets": 1,
            "consideration_shares": 0,
            "transaction_type": "acquisition",
        })

        # 600/100 * 100 = 600%
        assert result["ratios"]["consideration_ratio"] == 600.0
        assert any("500" in w or "unusual" in w.lower() for w in result["warnings"])

    def test_input_validation_rejects_missing_required(self, tool):
        """validate_inputs catches missing required fields."""
        errors = tool.validate_inputs({})
        assert len(errors) > 0
        assert any("transaction_consideration" in e for e in errors)
