"""Sprint 1: QueryParser Module Tests - 59 tests"""
import pytest
from app.tools.query_parser import QueryParser


class TestExtractNumbers:
    def test_simple_integers(self):
        assert QueryParser.extract_numbers("100 and 200") == [100.0, 200.0]
    def test_thousands_with_comma(self):
        result = QueryParser.extract_numbers("1,000,000 or 2.5")
        assert sorted(result) == [2.5, 1000000.0]
    def test_thousands_with_space(self):
        assert QueryParser.extract_numbers("1 000 000 HK$") == [1000000.0]
    def test_percentages_as_numbers(self):
        result = QueryParser.extract_numbers("0.5% or 1.5%")
        assert sorted(result) == [0.5, 1.5]
    def test_negative_numbers(self):
        result = QueryParser.extract_numbers("-100 to 200")
        assert sorted(result) == [-100.0, 200.0]
    def test_scientific_notation(self):
        assert QueryParser.extract_numbers("1e6") == [1000000.0]
    def test_no_numbers(self):
        assert QueryParser.extract_numbers("no numbers") == []
    def test_deduplicate_numbers(self):
        result = QueryParser.extract_numbers("100, 100, 200")
        assert sorted(result) == [100.0, 200.0]
    def test_decimal_comma(self):
        assert QueryParser.extract_numbers("1,234.56") == [1234.56]
    def test_empty_string(self):
        assert QueryParser.extract_numbers("") == []


class TestExtractCurrencyValues:
    def test_hk_dollars_million(self):
        result = QueryParser.extract_currency_values("HK$ 500 million")
        assert "hk_dollars" in result
    def test_usd_million(self):
        result = QueryParser.extract_currency_values("USD 10 million")
        assert "usd" in result
    def test_currency_after_amount(self):
        result = QueryParser.extract_currency_values("100 million HK$")
        assert "hk_dollars" in result
    def test_billion_suffix(self):
        result = QueryParser.extract_currency_values("1.5bn")
        assert len(result) > 0
    def test_thousand_suffix(self):
        result = QueryParser.extract_currency_values("500k")
        assert len(result) > 0
    def test_multiple_currencies(self):
        result = QueryParser.extract_currency_values("HK$ 1bn, USD 100m")
        assert ("hk_dollars" in result) or ("usd" in result)
    def test_raw_numbers_only(self):
        result = QueryParser.extract_currency_values("500")
        assert len(result) > 0
    def test_rmb_currency(self):
        result = QueryParser.extract_currency_values("RMB 100m")
        assert len(result) > 0
    def test_inferred_million(self):
        result = QueryParser.extract_currency_values("HK$m 500")
        assert len(result) > 0
    def test_empty_currency(self):
        result = QueryParser.extract_currency_values("")
        assert isinstance(result, dict)


class TestExtractPercentages:
    def test_simple_percent(self):
        assert QueryParser.extract_percentages("25%") == [25.0]
    def test_percent_word(self):
        assert QueryParser.extract_percentages("0.5 percent") == [0.5]
    def test_high_precision(self):
        assert QueryParser.extract_percentages("99.9%") == [99.9]
    def test_multiple_percentages(self):
        result = QueryParser.extract_percentages("25% and 50%")
        assert sorted(result) == [25.0, 50.0]
    def test_no_percentages(self):
        assert QueryParser.extract_percentages("no percentages") == []
    def test_percent_in_context(self):
        assert 100.0 in QueryParser.extract_percentages("100% increase")
    def test_chinese_percentage(self):
        assert 25.0 in QueryParser.extract_percentages("百分之25")
    def test_percentage_word_decimal(self):
        assert 0.1 in QueryParser.extract_percentages("0.1 percentage")


class TestExtractTransactionType:
    def test_acquiring(self):
        assert QueryParser.extract_transaction_type("acquiring company") == "acquisition"
    def test_sell(self):
        assert QueryParser.extract_transaction_type("sell shares") == "disposal"
    def test_purchase(self):
        assert QueryParser.extract_transaction_type("purchase assets") == "acquisition"
    def test_divest(self):
        assert QueryParser.extract_transaction_type("divesting subsidiary") == "disposal"
    def test_consolidation(self):
        assert QueryParser.extract_transaction_type("consolidation") == "acquisition"
    def test_takeover(self):
        assert QueryParser.extract_transaction_type("takeover bid") == "acquisition"
    def test_no_type(self):
        assert QueryParser.extract_transaction_type("reporting rules") is None
    def test_word_boundary(self):
        result = QueryParser.extract_transaction_type("discussing acquiring")
        assert result in [None, "acquisition"]


class TestExtractClassificationTier:
    def test_major(self):
        assert QueryParser.extract_classification_tier("major transaction") == "major_transaction"
    def test_very_substantial(self):
        assert QueryParser.extract_classification_tier("very substantial") == "very_substantial"
    def test_de_minimis(self):
        assert QueryParser.extract_classification_tier("de minimis") == "de_minimis"
    def test_discloseable(self):
        assert QueryParser.extract_classification_tier("discloseable transaction") == "discloseable_transaction"
    def test_share(self):
        assert QueryParser.extract_classification_tier("share transaction") == "share_transaction"
    def test_no_tier(self):
        assert QueryParser.extract_classification_tier("no tier") is None
    def test_word_boundary_majority(self):
        assert QueryParser.extract_classification_tier("majority") is None
    def test_major_in_sentence(self):
        assert QueryParser.extract_classification_tier("This is major") == "major_transaction"


class TestExtractRuleReference:
    def test_rule_decimal(self):
        assert QueryParser.extract_rule_reference("Rule 14.34") == "14.34"
    def test_rule_letter_decimal(self):
        assert QueryParser.extract_rule_reference("Rule 14A.35") == "14A.35"
    def test_bare_rule(self):
        assert QueryParser.extract_rule_reference("14.04") == "14.04"
    def test_section_prefix(self):
        assert QueryParser.extract_rule_reference("Section 14.58") == "14.58"
    def test_first_rule_multiple(self):
        assert QueryParser.extract_rule_reference("Rule 14.34 and Rule 14.38") == "14.34"
    def test_no_rules(self):
        assert QueryParser.extract_rule_reference("No rules") is None
    def test_chapter_rejected(self):
        assert QueryParser.extract_rule_reference("Chapter 14") is None
    def test_chapter_letter(self):
        assert QueryParser.extract_rule_reference("14A.46") == "14A.46"
    def test_chinese_rule(self):
        assert QueryParser.extract_rule_reference("规则14.34") == "14.34"
    def test_reject_invalid(self):
        assert QueryParser.extract_rule_reference("14.58a") is None


class TestNormalizeFieldName:
    def test_market_cap_variant(self):
        assert QueryParser.normalize_field_name("issuer market cap") == "issuer_market_cap"
    def test_already_normalized(self):
        assert QueryParser.normalize_field_name("transaction_consideration") == "transaction_consideration"
    def test_uppercase_spaces(self):
        assert QueryParser.normalize_field_name("ACQUIRED PROFIT") == "acquired_profit"
    def test_market_cap_short(self):
        assert QueryParser.normalize_field_name("market cap") == "issuer_market_cap"
    def test_mixed_case_spaces(self):
        assert QueryParser.normalize_field_name("Transaction Consideration") == "transaction_consideration"
