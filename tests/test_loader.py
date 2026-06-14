"""Tests for document loading and saving utilities."""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.loader import save_document, load_document_from_json
from app.schemas.document import Document, DocumentMetadata


def test_save_document_round_trip(tmp_path):
    doc = Document(
        document_id="test-doc-1",
        source_path="/tmp/test.md",
        source_type="md",
        title="Test Document",
        raw_text="Hello",
        cleaned_text="Hello",
        metadata=DocumentMetadata(
            imported_at=datetime(2024, 1, 15, 8, 30, 0, tzinfo=timezone.utc),
            source_url="https://example.com",
            page_count=5,
        ),
    )

    output_path = save_document(doc, tmp_path)
    assert output_path.exists()

    restored = load_document_from_json(output_path)
    assert restored.document_id == doc.document_id
    assert restored.metadata.imported_at == doc.metadata.imported_at
    assert restored.metadata.source_url == doc.metadata.source_url
    assert restored.metadata.page_count == doc.metadata.page_count


def test_save_document_stores_datetime_as_iso_string(tmp_path):
    doc = Document(
        document_id="dt-check",
        source_path="x",
        source_type="md",
        title="x",
        metadata=DocumentMetadata(imported_at=datetime(2024, 6, 14, 12, 0, 0, tzinfo=timezone.utc)),
    )

    output_path = save_document(doc, tmp_path)

    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data["metadata"]["imported_at"], str)
    assert "2024-06-14T12:00:00" in data["metadata"]["imported_at"]


def test_load_document_from_json_backwards_compatible_with_isoformat(tmp_path):
    """Old files saved via manual .isoformat() should still load correctly."""
    old_format = {
        "document_id": "legacy-doc",
        "source_path": "/legacy/path.md",
        "source_type": "md",
        "title": "Legacy Document",
        "raw_text": "legacy text",
        "cleaned_text": "",
        "metadata": {
            "imported_at": "2024-01-15T08:30:00",
            "source_url": None,
            "page_count": None,
        },
    }

    file_path = tmp_path / "legacy-doc.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(old_format, f)

    restored = load_document_from_json(file_path)
    assert restored.document_id == "legacy-doc"
    assert restored.metadata.imported_at == datetime(2024, 1, 15, 8, 30, 0)
