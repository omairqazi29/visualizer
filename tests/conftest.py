"""Shared synthetic fixtures for unit tests.

These provide minimal DataFrames that don't require live data files,
enabling fast, isolated testing of engine and domain logic.
"""

import pytest
import pandas as pd


@pytest.fixture
def sample_dos_df() -> pd.DataFrame:
    """Minimal DOS IV issuance DataFrame for unit tests.

    Contains a small set of rows covering FB, EB-1, and EB-4/5 categories
    with realistic column names matching DOSParser output.
    """
    data = [
        # FB categories
        {"chargeability": "Mexico", "visa_category": "F1", "count": 20000, "report_month": 1, "report_year": 2025},
        {"chargeability": "Philippines", "visa_category": "F2A", "count": 15000, "report_month": 1, "report_year": 2025},
        {"chargeability": "Dominican Republic", "visa_category": "F2B", "count": 10000, "report_month": 2, "report_year": 2025},
        {"chargeability": "India", "visa_category": "F3", "count": 5000, "report_month": 3, "report_year": 2025},
        {"chargeability": "China - mainland born", "visa_category": "F4", "count": 8000, "report_month": 4, "report_year": 2025},
        {"chargeability": "Vietnam", "visa_category": "FX", "count": 3000, "report_month": 5, "report_year": 2025},
        # EB-1 categories
        {"chargeability": "India", "visa_category": "E11", "count": 3000, "report_month": 1, "report_year": 2025},
        {"chargeability": "India", "visa_category": "E12", "count": 2000, "report_month": 2, "report_year": 2025},
        {"chargeability": "China - mainland born", "visa_category": "E13", "count": 1500, "report_month": 3, "report_year": 2025},
        {"chargeability": "United Kingdom", "visa_category": "E11", "count": 800, "report_month": 4, "report_year": 2025},
        # EB-4/5 categories
        {"chargeability": "El Salvador", "visa_category": "SD", "count": 500, "report_month": 1, "report_year": 2025},
        {"chargeability": "Guatemala", "visa_category": "SE", "count": 300, "report_month": 2, "report_year": 2025},
        {"chargeability": "India", "visa_category": "C5", "count": 200, "report_month": 3, "report_year": 2025},
        {"chargeability": "China - mainland born", "visa_category": "I5", "count": 1000, "report_month": 4, "report_year": 2025},
    ]
    return pd.DataFrame(data)


@pytest.fixture
def sample_inventory_stats() -> dict:
    """Minimal India EB-1 inventory stats matching InventoryParser.get_india_eb1_queue() shape.

    Values are illustrative (not from live data) for deterministic unit tests.
    """
    return {
        "mountain": 39127,
        "valley": 9035,
        "total": 48162,
    }


@pytest.fixture
def sample_inventory_df() -> pd.DataFrame:
    """Synthetic inventory DataFrame mimicking USCIS EB Inventory format.

    Includes a Preference Category column and Priority Date Year columns,
    with 'D' values for disclosure handling tests.
    """
    data = [
        {
            "Preference Category": "Employment-Based 1st Preference Category (EB1)",
            "Prior Years": 50,
            "Priority Date Year - 2020": 100,
            "Priority Date Year - 2021": "D",
            "Priority Date Year - 2022": 200,
            "Priority Date Year - 2023": 150,
            "Priority Date Year - 2024": 300,
            "Priority Date Year - 2025": 100,
        },
        {
            "Preference Category": "Employment-Based 2nd Preference Category (EB2)",
            "Prior Years": 30,
            "Priority Date Year - 2020": 80,
            "Priority Date Year - 2021": 90,
            "Priority Date Year - 2022": 70,
            "Priority Date Year - 2023": 60,
            "Priority Date Year - 2024": 50,
            "Priority Date Year - 2025": 40,
        },
        {
            "Preference Category": "Employment-Based 1st Preference Category (EB1)",
            "Prior Years": 10,
            "Priority Date Year - 2020": 20,
            "Priority Date Year - 2021": 30,
            "Priority Date Year - 2022": "-",
            "Priority Date Year - 2023": 40,
            "Priority Date Year - 2024": 50,
            "Priority Date Year - 2025": 60,
        },
    ]
    return pd.DataFrame(data)


@pytest.fixture
def sample_pipeline_df() -> pd.DataFrame:
    """Synthetic pipeline DataFrame mimicking I-140 performance report.

    Includes a Country column and EB-1 category column with realistic values.
    """
    data = [
        {"Country": "India", "1st Preference": 5000, "2nd Preference": 8000, "TOTAL": 13000},
        {"Country": "China", "1st Preference": 2000, "2nd Preference": 3000, "TOTAL": 5000},
        {"Country": "Philippines", "1st Preference": "D", "2nd Preference": 500, "TOTAL": 500},
        {"Country": "All Other", "1st Preference": 1000, "2nd Preference": 2000, "TOTAL": 3000},
    ]
    return pd.DataFrame(data)


@pytest.fixture
def sample_raw_dos_df() -> pd.DataFrame:
    """Synthetic raw DOS DataFrame before normalization.

    Has original column names that need header normalization.
    """
    data = [
        {"Foreign State of Chargeability": "India", "Visa Class": "E11", "Issuances": 100},
        {"Foreign State of Chargeability": "China", "Visa Class": "E12", "Issuances": "D"},
        {"Foreign State of Chargeability": "Mexico", "Visa Class": "F1", "Issuances": "<10"},
    ]
    return pd.DataFrame(data)
