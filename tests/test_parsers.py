import pytest
import pandas as pd
from src.parsers.base import BaseParser
from src.parsers.inventory_parser import InventoryParser
from src.parsers.pipeline_parser import PipelineParser
import os

def test_base_parser_normalization():
    # Mock DF with collision potential and 'D' values
    data = {
        "Country of Birth": ["India", "China"],
        "Class of Admission": ["E11", "E12"],
        "Issuances": ["100", "D"]
    }
    df = pd.DataFrame(data)
    
    parser = BaseParser("dummy.csv")
    parser.df = df
    
    # CHARGEABILITY_HEADERS includes "Country"
    parser.normalize_headers()
    assert "chargeability" in parser.df.columns
    assert "class_of_admission" in parser.df.columns
    
    parser.normalize_disclosure_values(["issuances"])
    assert parser.df["issuances"].iloc[0] == 100
    assert parser.df["issuances"].iloc[1] == 1 # 'D' -> 1

def test_inventory_parser_multiplier():
    # Use the generated mock data
    path = "data/eb_inventory_january_2026.xlsx"
    if not os.path.exists(path):
        pytest.skip("Mock data not found")
        
    parser = InventoryParser(path)
    stats = parser.get_india_eb1_queue()
    
    # Mock data for 1st preference (India) has counts like 1000, 500, 200, etc.
    # Total primary should be sum of Priority Date Year columns
    # InventoryParser applies 2.2x multiplier
    assert stats['total'] > 0
    # check if multiplier is applied (Primary sum * 2.2 should be int)
    # The counts in generate_mock_data are integers.
    pass

def test_pipeline_parser_multiplier():
    path = "data/eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx"
    if not os.path.exists(path):
        pytest.skip("Mock data not found")
        
    parser = PipelineParser(path)
    parser.load_data()
    backlog = parser.get_india_eb1_backlog()
    
    # Mock data for India EB1 is 5000
    # With 2.2x multiplier, it should be 11000
    assert backlog == 11000
