"""DisclosureChecklistTool — Generates a structured disclosure checklist for
HKEX notifiable / connected transactions.

Sections: pre_announcement, announcement, circular (if needed),
shareholder_meeting (if needed), post_completion.
Each item: task, required, deadline_days, rule_reference.
"""

from typing import Dict, Any, List

from app.tools.base_tool import BaseTool


# ── Checklist data ───────────────────────────────────────────────

def _announcement_items() -> List[Dict[str, Any]]:
    return [
        {"task": "Publish announcement on HKEXnews", "required": True, "deadline_days": 3, "rule_reference": "Rule 14.34"},
        {"task": "Include details of the transaction parties", "required": True, "deadline_days": 3, "rule_reference": "Rule 14.58"},
        {"task": "Disclose consideration and payment terms", "required": True, "deadline_days": 3, "rule_reference": "Rule 14.58"},
        {"task": "State size-test ratios and classification", "required": True, "deadline_days": 3, "rule_reference": "Rule 14.58"},
    ]


def _circular_items() -> List[Dict[str, Any]]:
    return [
        {"task": "Despatch circular to shareholders", "required": True, "deadline_days": 15, "rule_reference": "Rule 14.38A"},
        {"task": "Include letter from the Board", "required": True, "deadline_days": 15, "rule_reference": "Rule 14.63"},
        {"task": "Attach accountants report (if applicable)", "required": False, "deadline_days": 15, "rule_reference": "Rule 14.67"},
    ]


def _shareholder_meeting_items() -> List[Dict[str, Any]]:
    return [
        {"task": "Convene extraordinary general meeting (EGM)", "required": True, "deadline_days": 21, "rule_reference": "Rule 14.52"},
        {"task": "Obtain shareholder approval by poll", "required": True, "deadline_days": 21, "rule_reference": "Rule 14.52"},
    ]


def _very_substantial_extras() -> List[Dict[str, Any]]:
    return [
        {"task": "Include 3-year financial statements in circular", "required": True, "deadline_days": 15, "rule_reference": "Rule 14.69"},
        {"task": "Include pro forma financial information", "required": True, "deadline_days": 15, "rule_reference": "Rule 14.69"},
        {"task": "Include valuation report (if property)", "required": False, "deadline_days": 15, "rule_reference": "Rule 14.69"},
    ]


def _post_completion_items() -> List[Dict[str, Any]]:
    return [
        {"task": "Publish completion announcement", "required": True, "deadline_days": 3, "rule_reference": "Rule 14.36"},
    ]


def _connected_overlay_items() -> List[Dict[str, Any]]:
    return [
        {"task": "Appoint IFA (Independent Financial Adviser)", "required": True, "deadline_days": 7, "rule_reference": "Rule 14A.46"},
        {"task": "Obtain IFA opinion letter for circular", "required": True, "deadline_days": 15, "rule_reference": "Rule 14A.46"},
        {"task": "Obtain independent shareholder approval", "required": True, "deadline_days": 21, "rule_reference": "Rule 14A.36"},
        {"task": "Connected person(s) abstain from voting", "required": True, "deadline_days": 21, "rule_reference": "Rule 14A.36"},
        {"task": "Disclose connected party relationship details", "required": True, "deadline_days": 3, "rule_reference": "Rule 14A.68"},
    ]


def _de_minimis_items() -> List[Dict[str, Any]]:
    return [
        {"task": "Disclose in next annual report", "required": True, "deadline_days": 0, "rule_reference": "Rule 14.04"},
    ]


# ── Tool class ───────────────────────────────────────────────────

class DisclosureChecklistTool(BaseTool):

    @property
    def name(self) -> str:
        return "disclosure_checklist"

    @property
    def description(self) -> str:
        return (
            "Generates a structured disclosure checklist for an HKEX notifiable "
            "or connected transaction, listing required tasks, deadlines, and "
            "rule references grouped by stage (announcement, circular, meeting, etc.)."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "classification": {
                    "type": "string",
                    "description": "Transaction classification (de_minimis, share_transaction, discloseable_transaction, major_transaction, very_substantial)",
                },
                "is_connected": {
                    "type": "boolean",
                    "description": "Whether this is a connected transaction",
                },
                "shareholder_vote_required": {
                    "type": "boolean",
                    "description": "Whether shareholder vote is required",
                },
            },
            "required": ["classification", "is_connected", "shareholder_vote_required"],
        }

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        errors = self.validate_inputs(inputs)
        if errors:
            return {"error": "; ".join(errors), "sections": []}

        classification: str = inputs["classification"]
        is_connected: bool = inputs["is_connected"]
        shareholder_vote_required: bool = inputs["shareholder_vote_required"]

        sections: List[Dict[str, Any]] = []

        # ── De minimis — minimal disclosure ──────────────────────
        if classification == "de_minimis":
            sections.append({"name": "post_completion", "items": _de_minimis_items()})
            if is_connected:
                sections = self._add_connected_overlay(sections, shareholder_vote_required)
            return {"classification": classification, "sections": sections}

        # ── Announcement (share_transaction and above) ───────────
        sections.append({"name": "announcement", "items": _announcement_items()})

        # ── Circular (discloseable and above) ────────────────────
        needs_circular = classification in (
            "discloseable_transaction", "major_transaction", "very_substantial"
        )
        if needs_circular:
            circular_items = _circular_items()
            if classification == "very_substantial":
                circular_items.extend(_very_substantial_extras())
            sections.append({"name": "circular", "items": circular_items})

        # ── Shareholder meeting (major and above) ────────────────
        if shareholder_vote_required:
            sections.append({"name": "shareholder_meeting", "items": _shareholder_meeting_items()})

        # ── Post completion ──────────────────────────────────────
        sections.append({"name": "post_completion", "items": _post_completion_items()})

        # ── Connected overlay ────────────────────────────────────
        if is_connected:
            sections = self._add_connected_overlay(sections, shareholder_vote_required)

        return {"classification": classification, "sections": sections}

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _add_connected_overlay(
        sections: List[Dict[str, Any]],
        shareholder_vote_required: bool,
    ) -> List[Dict[str, Any]]:
        """Inject connected-transaction items into existing sections."""
        section_names = {s["name"] for s in sections}

        # Make sure circular and shareholder_meeting exist
        if "circular" not in section_names:
            sections.insert(-1, {"name": "circular", "items": _circular_items()})
        if "shareholder_meeting" not in section_names:
            sections.insert(-1, {"name": "shareholder_meeting", "items": _shareholder_meeting_items()})

        # Add connected-specific items to announcement section (or create one)
        connected_items = _connected_overlay_items()

        # Distribute connected items into relevant sections
        for s in sections:
            if s["name"] == "announcement":
                s["items"].extend([
                    i for i in connected_items if i["deadline_days"] <= 3
                ])
            elif s["name"] == "circular":
                s["items"].extend([
                    i for i in connected_items
                    if i["deadline_days"] > 3 and i["deadline_days"] <= 15
                ])
            elif s["name"] == "shareholder_meeting":
                s["items"].extend([
                    i for i in connected_items if i["deadline_days"] > 15
                ])

        return sections
