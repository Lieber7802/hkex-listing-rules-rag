"""Tests for DisclosureChecklistTool (Sprint 4).

Generates a structured disclosure checklist based on classification,
connected status, and shareholder vote requirement.
"""

import pytest
from app.tools.disclosure_checklist import DisclosureChecklistTool


@pytest.fixture
def tool():
    return DisclosureChecklistTool()


# ── Interface ────────────────────────────────────────────────────

class TestChecklistInterface:

    def test_name(self, tool):
        assert tool.name == "disclosure_checklist"

    def test_description_non_empty(self, tool):
        assert len(tool.description) > 10

    def test_input_schema_has_required_fields(self, tool):
        schema = tool.input_schema
        assert "classification" in schema["required"]
        assert "is_connected" in schema["required"]


# ── De minimis ───────────────────────────────────────────────────

class TestDeMinimis:

    def test_de_minimis_has_sections(self, tool):
        r = tool.run({
            "classification": "de_minimis",
            "is_connected": False,
            "shareholder_vote_required": False,
        })
        assert "sections" in r
        assert len(r["sections"]) >= 1

    def test_de_minimis_no_circular(self, tool):
        r = tool.run({
            "classification": "de_minimis",
            "is_connected": False,
            "shareholder_vote_required": False,
        })
        section_names = [s["name"] for s in r["sections"]]
        assert "circular" not in section_names


# ── Share transaction ────────────────────────────────────────────

class TestShareTransaction:

    def test_share_transaction_has_announcement(self, tool):
        r = tool.run({
            "classification": "share_transaction",
            "is_connected": False,
            "shareholder_vote_required": False,
        })
        section_names = [s["name"] for s in r["sections"]]
        assert "announcement" in section_names


# ── Major transaction ────────────────────────────────────────────

class TestMajorTransaction:

    def test_major_includes_circular(self, tool):
        r = tool.run({
            "classification": "major_transaction",
            "is_connected": False,
            "shareholder_vote_required": True,
        })
        section_names = [s["name"] for s in r["sections"]]
        assert "circular" in section_names

    def test_major_includes_shareholder_meeting(self, tool):
        r = tool.run({
            "classification": "major_transaction",
            "is_connected": False,
            "shareholder_vote_required": True,
        })
        section_names = [s["name"] for s in r["sections"]]
        assert "shareholder_meeting" in section_names


# ── Very substantial ─────────────────────────────────────────────

class TestVerySubstantial:

    def test_very_substantial_has_all_sections(self, tool):
        r = tool.run({
            "classification": "very_substantial",
            "is_connected": False,
            "shareholder_vote_required": True,
        })
        section_names = [s["name"] for s in r["sections"]]
        assert "announcement" in section_names
        assert "circular" in section_names
        assert "post_completion" in section_names

    def test_very_substantial_items_have_rule_reference(self, tool):
        r = tool.run({
            "classification": "very_substantial",
            "is_connected": False,
            "shareholder_vote_required": True,
        })
        for section in r["sections"]:
            for item in section["items"]:
                assert "rule_reference" in item


# ── Connected overlay ────────────────────────────────────────────

class TestConnectedOverlay:

    def test_connected_adds_ifa_items(self, tool):
        r = tool.run({
            "classification": "share_transaction",
            "is_connected": True,
            "shareholder_vote_required": True,
        })
        all_tasks = []
        for section in r["sections"]:
            all_tasks.extend([item["task"] for item in section["items"]])
        # Should mention IFA somewhere
        assert any("IFA" in t or "independent financial" in t.lower() for t in all_tasks)

    def test_connected_adds_14a_rule_refs(self, tool):
        r = tool.run({
            "classification": "share_transaction",
            "is_connected": True,
            "shareholder_vote_required": True,
        })
        all_refs = []
        for section in r["sections"]:
            all_refs.extend([item["rule_reference"] for item in section["items"]])
        assert any("14A" in ref for ref in all_refs)

    def test_connected_includes_shareholder_meeting(self, tool):
        """Connected transactions always require independent shareholder approval."""
        r = tool.run({
            "classification": "share_transaction",
            "is_connected": True,
            "shareholder_vote_required": True,
        })
        section_names = [s["name"] for s in r["sections"]]
        assert "shareholder_meeting" in section_names


# ── Item structure ───────────────────────────────────────────────

class TestItemStructure:

    def test_items_have_required_fields(self, tool):
        r = tool.run({
            "classification": "major_transaction",
            "is_connected": False,
            "shareholder_vote_required": True,
        })
        for section in r["sections"]:
            for item in section["items"]:
                assert "task" in item
                assert "required" in item
                assert "rule_reference" in item
