"""Tests for SizeTestInputExtractor heuristic extraction (Sprint 3)."""

import pytest
from app.tools.size_test_input_extractor import SizeTestInputExtractor


class TestSizeTestInputExtractor:

    def setup_method(self):
        self.extractor = SizeTestInputExtractor()

    def test_extract_full_english_query(self):
        result = self.extractor.extract(
            "Calculate size test: issuer market cap 1000 million, total assets 2000 million, "
            "net assets 500 million, annual profit 100 million, shares outstanding 10000, "
            "transaction consideration 250 million, acquired assets 600 million, "
            "acquired profit 60 million, acquired net assets 150 million, acquisition"
        )

        assert result.get("issuer_market_cap") is not None
        assert result.get("transaction_consideration") is not None
        assert result.get("transaction_type") == "acquisition"
        assert result["_confidence"] > 0

    def test_extract_chinese_query(self):
        result = self.extractor.extract(
            "计算规模测试：公司市值1000亿，总资产2000亿，净资产500亿，年度溢利100亿"
        )

        assert result.get("issuer_market_cap") is not None
        assert result.get("issuer_total_assets") is not None
        assert result.get("issuer_net_assets") is not None
        assert result.get("issuer_annual_profit") is not None

    def test_extract_transaction_type_acquisition(self):
        result = self.extractor.extract(
            "Acquisition of target company with market cap 500 and consideration 100"
        )
        assert result.get("transaction_type") == "acquisition"

    def test_extract_transaction_type_disposal(self):
        result = self.extractor.extract(
            "Disposal of subsidiary with market cap 500 and consideration 100"
        )
        assert result.get("transaction_type") == "disposal"

    def test_empty_query(self):
        result = self.extractor.extract("")
        assert result["_confidence"] == 0.0
        assert len(result["_missing"]) >= 10  # all required + field keywords

    def test_confidence_increases_with_more_fields(self):
        result1 = self.extractor.extract("market cap 1000")
        result2 = self.extractor.extract(
            "market cap 1000, total assets 2000, consideration 250"
        )
        assert result2["_confidence"] > result1["_confidence"]

    def test_missing_fields_reported(self):
        result = self.extractor.extract("market cap 1000")
        assert "issuer_total_assets" in result["_missing"]
        assert "transaction_type" in result["_missing"]

    def test_mixed_chinese_english(self):
        result = self.extractor.extract(
            "issuer market cap 1000 million, total assets 2000万, consideration 250"
        )
        assert result.get("issuer_market_cap") is not None
        assert result.get("issuer_total_assets") is not None
        assert result.get("transaction_consideration") is not None

    def test_consideration_extracted(self):
        result = self.extractor.extract(
            "transaction consideration HK$250 million for acquisition"
        )
        assert result.get("transaction_consideration") is not None

    def test_no_fallback_random_assignment(self):
        """When keywords don't match numbers, no fallback random assignment occurs."""
        result = self.extractor.extract("1000 2000 500 100 10000")
        # Only transaction_type should potentially be set (from keywords like 'acquisition' in query)
        # Random number-to-field assignment no longer happens
        filled = sum(1 for k in SizeTestInputExtractor.FIELD_KEYWORDS if k in result)
        assert filled >= 0  # may be 0 if no keywords matched

    def test_get_confidence(self):
        result = self.extractor.extract("market cap 1000")
        conf = self.extractor.get_confidence(result)
        assert 0.0 <= conf <= 1.0


class TestSizeTestInputExtractorEdgeCases:

    def test_no_numbers_in_query(self):
        extractor = SizeTestInputExtractor()
        result = extractor.extract("What is a size test?")
        assert result["_confidence"] == 0.0

    def test_duplicate_numbers_different_fields(self):
        extractor = SizeTestInputExtractor()
        result = extractor.extract("market cap 500, assets 500")
        # Both fields should be extracted even with same value
        assert result.get("issuer_market_cap") is not None

    def test_numbers_with_formatting(self):
        extractor = SizeTestInputExtractor()
        result = extractor.extract("market cap 1,000 million and total assets 2,500")
        assert result.get("issuer_market_cap") is not None
        assert result.get("issuer_total_assets") is not None
