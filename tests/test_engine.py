import pytest
from datetime import datetime
from src.engine.demand import DemandModeler
from src.engine.redistribution import RedistributionEngine
import pandas as pd

def test_demand_modeler_confidence():
    # Total queue 100,000, annual supply 24,000, even distribution (2000/mo)
    dist = {m: 1/12 for m in range(1, 13)}
    modeler = DemandModeler(inventory_total=100000, annual_supply=24000, monthly_distribution=dist)
    
    # User with 10,000 backlog ahead -> clears in 5 months
    pd_date = datetime(2025, 1, 1)
    score_high = modeler.calculate_confidence_score(pd_date, backlog_ahead=10000, target_fy=2027)
    assert score_high > 0.9
    
    # User with 80,000 backlog ahead -> clears in 40 months -> ~3.3 years
    score_low = modeler.calculate_confidence_score(pd_date, backlog_ahead=80000, target_fy=2027)
    assert score_low < 0.5

def test_demand_modeler_nonlinear():
    # Backlog 10,000. Annual supply 10,000.
    # 90% of visas issued in September (Month 9).
    dist = {m: 0.01 for m in range(1, 13)}
    dist[9] = 0.89 # Total 1.0
    
    # If we start in January, it should take until September to clear most of it
    modeler = DemandModeler(inventory_total=10000, annual_supply=10000, monthly_distribution=dist)
    start_date = datetime(2026, 1, 1)
    projection = modeler.project_clearance(start_date=start_date)
    
    # After 1 month (Feb), only 100 cleared (1% of 10k)
    assert projection["trajectory"][1]["backlog"] == 9900
    # Clearance should be at least 9 months away (Sept 2026 or later)
    # Jan 2026 + 9 months = Oct 2026.
    assert projection["months_to_clear"] >= 9

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
