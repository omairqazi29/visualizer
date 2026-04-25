import pytest
import pandas as pd
import os
from src.parsers.base import BaseParser

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
