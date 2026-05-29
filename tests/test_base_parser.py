import pytest
import pandas as pd
import os
from src.parsers.base import BaseParser, ParserUtils


# ─── Existing tests (preserved) ────────────────────────────────────────────

def test_normalize_headers():
    df = pd.DataFrame({
        "Foreign State of Chargeability": ["India", "China"],
        "Place of Birth": ["India", "China"],
        "Some Other Column": [1, 2]
    })
    # We need to save it to a temp file to use the loader or just set df directly
    parser = BaseParser("dummy.csv")
    parser.df = df
    parser.normalize_headers()
    
    assert "chargeability" in parser.df.columns
    assert "some_other_column" in parser.df.columns

def test_normalize_disclosure_values():
    df = pd.DataFrame({
        "count": [10, "D", " 5 ", "D", "abc"]
    })
    parser = BaseParser("dummy.csv")
    parser.df = df
    parser.normalize_disclosure_values(["count"])
    
    # "D" -> 1, " 5 " -> 5, "abc" -> 0
    expected = [10, 1, 5, 1, 0]
    assert list(parser.df["count"]) == expected


# ─── ParserUtils static method tests ───────────────────────────────────────

class TestParserUtilsNormalizeHeaders:
    """Tests for ParserUtils.normalize_headers (static, no parser instance needed)."""

    def test_chargeability_foreign_state(self):
        df = pd.DataFrame({"Foreign State": ["India"], "Count": [10]})
        result = ParserUtils.normalize_headers(df)
        assert "chargeability" in result.columns

    def test_chargeability_place_of_birth(self):
        df = pd.DataFrame({"Place of Birth": ["India"], "Count": [10]})
        result = ParserUtils.normalize_headers(df)
        assert "chargeability" in result.columns

    def test_chargeability_country(self):
        df = pd.DataFrame({"Country": ["India"], "Count": [10]})
        result = ParserUtils.normalize_headers(df)
        assert "chargeability" in result.columns

    def test_only_first_chargeability_mapped(self):
        """When multiple chargeability-like columns exist, only the first maps."""
        df = pd.DataFrame({
            "Foreign State of Chargeability": ["India"],
            "Country": ["India"],
        })
        result = ParserUtils.normalize_headers(df)
        cols = list(result.columns)
        assert cols.count("chargeability") == 1
        # Second column gets lowercased instead
        assert "country" in cols

    def test_spaces_and_dashes_normalized(self):
        df = pd.DataFrame({"Some-Column Name": [1], "Another Column": [2]})
        result = ParserUtils.normalize_headers(df)
        assert "some_column_name" in result.columns
        assert "another_column" in result.columns

    def test_leaked_header_row_filtered(self):
        """Rows containing the literal header name 'Foreign State of Chargeability' are removed."""
        df = pd.DataFrame({
            "Foreign State of Chargeability": ["Foreign State of Chargeability", "India"],
            "Count": [0, 100],
        })
        result = ParserUtils.normalize_headers(df)
        assert len(result) == 1
        assert result.iloc[0]["chargeability"] == "India"

    def test_whitespace_stripped_from_chargeability(self):
        df = pd.DataFrame({"Country": ["  India  ", " China"], "Val": [1, 2]})
        result = ParserUtils.normalize_headers(df)
        assert result.iloc[0]["chargeability"] == "India"
        assert result.iloc[1]["chargeability"] == "China"

    def test_returns_new_dataframe(self):
        """normalize_headers should not mutate the original DataFrame."""
        df = pd.DataFrame({"Country": ["India"], "Count": [10]})
        original_cols = list(df.columns)
        _ = ParserUtils.normalize_headers(df)
        assert list(df.columns) == original_cols


class TestParserUtilsNormalizeDisclosureValues:
    """Tests for ParserUtils.normalize_disclosure_values (static)."""

    def test_d_becomes_one(self):
        df = pd.DataFrame({"count": ["D"]})
        result = ParserUtils.normalize_disclosure_values(df, ["count"])
        assert result["count"].iloc[0] == 1

    def test_lowercase_d_becomes_one(self):
        df = pd.DataFrame({"count": ["d"]})
        result = ParserUtils.normalize_disclosure_values(df, ["count"])
        assert result["count"].iloc[0] == 1

    def test_less_than_midpoint(self):
        df = pd.DataFrame({"count": ["<10"]})
        result = ParserUtils.normalize_disclosure_values(df, ["count"])
        assert result["count"].iloc[0] == 5  # 10 // 2

    def test_less_than_20(self):
        df = pd.DataFrame({"count": ["<20"]})
        result = ParserUtils.normalize_disclosure_values(df, ["count"])
        assert result["count"].iloc[0] == 10  # 20 // 2

    def test_numeric_passthrough(self):
        df = pd.DataFrame({"count": [42, 100]})
        result = ParserUtils.normalize_disclosure_values(df, ["count"])
        assert list(result["count"]) == [42, 100]

    def test_non_numeric_string_becomes_zero(self):
        df = pd.DataFrame({"count": ["abc"]})
        result = ParserUtils.normalize_disclosure_values(df, ["count"])
        assert result["count"].iloc[0] == 0

    def test_missing_column_ignored(self):
        df = pd.DataFrame({"other": [1, 2]})
        result = ParserUtils.normalize_disclosure_values(df, ["count"])
        assert list(result["other"]) == [1, 2]

    def test_returns_new_dataframe(self):
        """normalize_disclosure_values should not mutate the original DataFrame."""
        df = pd.DataFrame({"count": ["D", 10]})
        original_vals = list(df["count"])
        _ = ParserUtils.normalize_disclosure_values(df, ["count"])
        assert list(df["count"]) == original_vals


class TestBaseParserClean:
    """Tests for BaseParser.clean() method."""

    def test_clean_normalizes_headers(self):
        df = pd.DataFrame({"Foreign State": ["India"], "Count": [10]})
        parser = BaseParser("dummy.csv")
        parser.df = df
        parser.clean()
        assert "chargeability" in parser.df.columns

    def test_clean_on_none_df(self):
        """clean() should not raise when df is None."""
        parser = BaseParser("dummy.csv")
        parser.clean()  # Should not raise
        assert parser.df is None


class TestBaseParserParse:
    """Tests for BaseParser.parse() method (Parser protocol compliance)."""

    def test_parse_with_csv(self, tmp_path):
        """parse() loads and cleans a CSV file, returning a DataFrame."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Country,Count\nIndia,100\nChina,200\n")
        parser = BaseParser(str(csv_file))
        result = parser.parse()
        assert isinstance(result, pd.DataFrame)
        assert "chargeability" in result.columns
        assert len(result) == 2

    def test_parse_sets_self_df(self, tmp_path):
        """parse() should also set self.df for backward compat."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Country,Count\nIndia,100\n")
        parser = BaseParser(str(csv_file))
        result = parser.parse()
        assert parser.df is not None
        assert parser.df is result
