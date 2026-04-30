"""Sprint 1: QueryParser Module Tests"""
import pytest
from app.tools.query_parser import QueryParser

class TestExtractNumbers:
    def test_simple_integers(self):
        result = QueryParser.extract_numbers("100 and 200")
        assert result == [100.0, 200.0]
    def test_thousands_with_comma(self):
        result = QueryParser.extract_numbers("1,000,000 or 2.5")
        assert sorted(result) == [2.5, 1000000.0]
    def test_thousands_with_space(self):
        result = QueryParser.extract_numbers("1 000 000 HK$")
        assert result == [1000000.0]
    def test_percentages_as_numbers(self):
        result = QueryParser.extract_numbers("0.5% or 1.5%")
        assert sorted(result) == [0.5, 1.5]
    def test_negative_numbers(self):
        result = QueryParser.extract_numbers("-100 to 200")
        assert sorted(result) == [-100.0, 200.0]
    def test_scientific_notation(self):
        result = QueryParser.extract_numbers("1e6")
        assert result == [1000000.0]
    def test_no_numbers(self):
        result = QueryParser.extract_numbers("no numbers")
        assert result == []
    def test_deduplicate_numbers(self):
        result = QueryParser.extract_numbers("100, 100, 200")
        assert sorted(result) == [100.0, 200.0]
    def test_decimal_with_comma_thousands(self):
        result = QueryParser.extract_numbers("1,234.56")
        assert result == [1234.56]
    def test_empty_string(self):
        result = QueryParser.extract_numbers("")
        assert result == []
