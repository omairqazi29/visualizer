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
