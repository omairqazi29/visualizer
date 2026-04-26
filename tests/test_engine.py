import pytest
from datetime import datetime
from src.engine.demand import DemandModeler
from src.engine.redistribution import RedistributionEngine
import pandas as pd

def test_demand_modeler_confidence():
    # Total queue 100,000, burn rate 2000/mo -> 50 months (~4.2 years)
    modeler = DemandModeler(inventory_total=100000, burn_rate=2000)
    
    # User with 10,000 backlog ahead -> clears in 5 months
    pd_date = datetime(2025, 1, 1)
    score_high = modeler.calculate_confidence_score(pd_date, backlog_ahead=10000, target_fy=2027)
    assert score_high > 0.9
    
    # User with 80,000 backlog ahead -> clears in 40 months -> ~3.3 years
    # 2026-04-25 + 3.3 years = ~2029 (Beyond FY 2027)
    score_low = modeler.calculate_confidence_score(pd_date, backlog_ahead=80000, target_fy=2027)
    assert score_low < 0.5

def test_redistribution_engine_cap():
    restricted = {"India", "China"}
    engine = RedistributionEngine(restricted, per_country_cap=0.07)
    
    data = {
        "chargeability": ["India", "China", "UK", "Canada"],
        "count": [10000, 5000, 20000, 1000]
    }
    df = pd.DataFrame(data)
    
    # Total limit 226,000 -> 7% cap is 15,820
    df_frozen = engine.apply_freeze(df, total_limit=226000)
    
    # Restricted countries should be 0
    assert df_frozen.loc[df_frozen['chargeability'] == "India", "count"].values[0] == 0
    assert df_frozen.loc[df_frozen['chargeability'] == "China", "count"].values[0] == 0
    
    # UK (20,000) is above cap (15,820) -> should be capped
    assert df_frozen.loc[df_frozen['chargeability'] == "UK", "count"].values[0] == 15820
    
    # Canada (1,000) is below cap -> should stay same
    assert df_frozen.loc[df_frozen['chargeability'] == "Canada", "count"].values[0] == 1000

def test_burn_rate_calculation():
    data = {"count": [1000, 2000, 3000]} # Total 6000
    df = pd.DataFrame(data)

    # 12 months average of 6000 -> 500
    burn_rate = DemandModeler.calculate_burn_rate_from_dos(df, months=12)
    assert burn_rate == 500

def test_burn_rate_filtering():
    data = {
        "chargeability": ["India", "India", "China", "India"],
        "visa_category": ["E11", "F4", "E11", "E12"],
        "count": [100, 500, 200, 300]
    }
    df = pd.DataFrame(data)

    # India EB-1 only (E11 + E12 = 100 + 300 = 400)
    # 12 months average of 400 -> 33
    burn_rate = DemandModeler.calculate_burn_rate_from_dos(
        df, 
        months=12, 
        country="India", 
        categories=["E11", "E12"]
    )
    assert burn_rate == 33

    # Unknown country should return default
    burn_rate_default = DemandModeler.calculate_burn_rate_from_dos(
        df, 
        months=12, 
        country="UK"
    )
    assert burn_rate_default == DemandModeler.DEFAULT_BURN_RATE
