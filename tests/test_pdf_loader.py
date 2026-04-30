"""Tests for PDF document loader (Sprint 2).

Tests:
- PDFLoader.can_load identifies .pdf files
- PDFLoader.can_load rejects non-PDF
- PDFLoader.load extracts text from valid PDF
- PDFLoader.load multi-page with [PAGE N] markers
- PDFLoader.load returns empty for corrupt file
- DocumentLoader integration: creates Document with raw_text from PDF
"""

import pytest
import tempfile
from pathlib import Path

from app.ingestion.loader import PDFLoader, DocumentLoader


def _check_pymupdf():
    try:
        import fitz
        return True
    except ImportError:
        return False


def _create_test_pdf(path: Path, pages: list) -> Path:
    """Create a minimal PDF with given page texts using pymupdf."""
    import fitz
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# ── can_load ─────────────────────────────────────────────────────

class TestPDFLoaderCanLoad:

    def test_accepts_pdf(self):
        assert PDFLoader().can_load(Path("doc.pdf")) is True

    def test_accepts_uppercase_pdf(self):
        assert PDFLoader().can_load(Path("doc.PDF")) is True

    def test_rejects_txt(self):
        assert PDFLoader().can_load(Path("doc.txt")) is False

    def test_rejects_md(self):
        assert PDFLoader().can_load(Path("doc.md")) is False


# ── load ─────────────────────────────────────────────────────────

@pytest.mark.skipif(not _check_pymupdf(), reason="pymupdf not installed")
class TestPDFLoaderLoad:

    def test_extracts_single_page(self, tmp_dir):
        pdf_path = _create_test_pdf(tmp_dir / "test.pdf", ["Hello HKEX World"])

        text = PDFLoader().load(pdf_path)

        assert "Hello HKEX World" in text
        assert "[PAGE 1]" in text

    def test_extracts_multi_page_with_markers(self, tmp_dir):
        pdf_path = _create_test_pdf(
            tmp_dir / "multi.pdf",
            ["Chapter 14 content", "Chapter 14A content"]
        )

        text = PDFLoader().load(pdf_path)

        assert "[PAGE 1]" in text
        assert "[PAGE 2]" in text
        assert "Chapter 14 content" in text
        assert "Chapter 14A content" in text

    def test_returns_empty_for_corrupt_file(self, tmp_dir):
        bad_pdf = tmp_dir / "corrupt.pdf"
        bad_pdf.write_bytes(b"this is not a pdf")

        text = PDFLoader().load(bad_pdf)

        assert text == ""

    def test_returns_empty_for_nonexistent_file(self, tmp_dir):
        text = PDFLoader().load(tmp_dir / "nonexistent.pdf")

        assert text == ""


# ── DocumentLoader integration ───────────────────────────────────

@pytest.mark.skipif(not _check_pymupdf(), reason="pymupdf not installed")
class TestDocumentLoaderPDFIntegration:

    def test_creates_document_with_raw_text(self, tmp_dir):
        pdf_path = _create_test_pdf(
            tmp_dir / "listing_rules.pdf",
            ["Rule 14.52 — Major Transactions"]
        )

        loader = DocumentLoader()
        doc = loader.load_document(pdf_path)

        assert doc is not None
        assert doc.source_type == "pdf"
        assert "Rule 14.52" in doc.raw_text
        assert len(doc.raw_text) > 0

    def test_returns_none_for_missing_file(self, tmp_dir):
        loader = DocumentLoader()
        doc = loader.load_document(tmp_dir / "no_such.pdf")

        assert doc is None
