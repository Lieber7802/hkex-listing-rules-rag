"""Tests for TransactionClassifierTool (Sprint 3).

Maps highest_ratio + transaction_type + connected status →
  classification, rules, disclosure level, shareholder vote, IFA, circular.
"""

import pytest
from app.tools.transaction_classifier import TransactionClassifierTool


@pytest.fixture
def tool():
    return TransactionClassifierTool()


# ── Interface ────────────────────────────────────────────────────

class TestClassifierInterface:

    def test_name(self, tool):
        assert tool.name == "transaction_classifier"

    def test_description_non_empty(self, tool):
        assert len(tool.description) > 10

    def test_input_schema_has_required_fields(self, tool):
        schema = tool.input_schema
        assert "highest_ratio" in schema["required"]
        assert "transaction_type" in schema["required"]
        assert "is_connected" in schema["required"]


# ── Classification tiers (acquisition, not connected) ────────────

class TestAcquisitionTiers:

    def _run(self, tool, ratio, txn_type="acquisition"):
        return tool.run({
            "highest_ratio": ratio,
            "transaction_type": txn_type,
            "is_connected": False,
        })

    def test_de_minimis(self, tool):
        r = self._run(tool, 3.0)
        assert r["classification"] == "de_minimis"
        assert r["shareholder_vote_required"] is False

    def test_share_transaction(self, tool):
        r = self._run(tool, 15.0)
        assert r["classification"] == "share_transaction"
        assert r["chapter"] == "Chapter 14"

    def test_discloseable(self, tool):
        r = self._run(tool, 30.0)
        assert r["classification"] == "discloseable_transaction"
        assert r["circular_required"] is True

    def test_major(self, tool):
        r = self._run(tool, 60.0)
        assert r["classification"] == "major_transaction"
        assert r["shareholder_vote_required"] is True
        assert r["circular_required"] is True

    def test_very_substantial(self, tool):
        r = self._run(tool, 120.0)
        assert r["classification"] == "very_substantial"
        assert r["shareholder_vote_required"] is True


# ── Disposal thresholds ──────────────────────────────────────────

class TestDisposalTiers:

    def test_disposal_major(self, tool):
        r = tool.run({
            "highest_ratio": 60.0,
            "transaction_type": "disposal",
            "is_connected": False,
        })
        assert r["classification"] == "major_transaction"

    def test_disposal_very_substantial_at_75(self, tool):
        r = tool.run({
            "highest_ratio": 75.0,
            "transaction_type": "disposal",
            "is_connected": False,
        })
        assert r["classification"] == "very_substantial"


# ── Connected transaction overrides ──────────────────────────────

class TestConnectedOverrides:

    def test_connected_forces_shareholder_vote(self, tool):
        r = tool.run({
            "highest_ratio": 10.0,
            "transaction_type": "acquisition",
            "is_connected": True,
            "connected_party_type": "director",
        })
        assert r["shareholder_vote_required"] is True

    def test_connected_forces_ifa(self, tool):
        r = tool.run({
            "highest_ratio": 10.0,
            "transaction_type": "acquisition",
            "is_connected": True,
            "connected_party_type": "substantial_shareholder",
        })
        assert r["ifa_required"] is True

    def test_connected_raises_disclosure_level(self, tool):
        r = tool.run({
            "highest_ratio": 10.0,
            "transaction_type": "acquisition",
            "is_connected": True,
            "connected_party_type": "director",
        })
        assert r["disclosure_level"] == "very_high"

    def test_connected_adds_chapter_14a_rules(self, tool):
        r = tool.run({
            "highest_ratio": 10.0,
            "transaction_type": "acquisition",
            "is_connected": True,
            "connected_party_type": "director",
        })
        assert any("14A" in rule for rule in r["applicable_rules"])

    def test_connected_override_recorded(self, tool):
        r = tool.run({
            "highest_ratio": 10.0,
            "transaction_type": "acquisition",
            "is_connected": True,
            "connected_party_type": "director",
        })
        assert r["connected_override"] is not None
