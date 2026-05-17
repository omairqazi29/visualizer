import pytest
from datetime import datetime
from src.engine.demand import DemandModeler
from src.engine.redistribution import RedistributionEngine
import pandas as pd

def test_demand_modeler_october_reset():
    # Annual supply 12,000 (1000/mo). Backlog 15,000.
    # Start in July (Month 7). 
    # July, Aug, Sept should issue 1000 each. Total 3000.
    # FY resets in October.
    dist = {m: 1/12 for m in range(1, 13)}
    modeler = DemandModeler(inventory_total=15000, annual_supply=12000, monthly_distribution=dist)
    
    start_date = datetime(2025, 7, 1)
    projection = modeler.project_clearance(start_date=start_date)
    
    # Oct 1 2025 is index 3 (July=0, Aug=1, Sept=2, Oct=3)
    # Check if Oct reset happened by looking at backlog change
    oct_backlog = projection["trajectory"][3]["backlog"] # End of Sept
    nov_backlog = projection["trajectory"][4]["backlog"] # End of Oct
    
    # Should have cleared 1000 in October
    assert oct_backlog - nov_backlog == 1000

def test_demand_modeler_exhaustion():
    # Annual supply 12,000. Backlog 20,000.
    # Force exhaustion by putting 100% in month 1 (Jan)
    dist = {m: 0 for m in range(1, 13)}
    dist[1] = 1.0
    
    modeler = DemandModeler(inventory_total=20000, annual_supply=12000, monthly_distribution=dist)
    start_date = datetime(2026, 1, 1)
    projection = modeler.project_clearance(start_date=start_date)
    
    # Trajectory[0] = Start (Jan 1, 20000)
    # Trajectory[1] = End of Jan (8000) - all 12000 used
    # Trajectory[2] = End of Feb (8000) - 0 used because FY exhausted
    # ...
    # Trajectory[9] = End of Sept (8000)
    # Trajectory[10] = End of Oct (8000) - Reset! But dist[10] is 0
    # Wait, my dist has 1.0 in Jan. So it will clear in next Jan.
    
    assert projection["trajectory"][1]["backlog"] == 8000
    assert projection["trajectory"][2]["backlog"] == 8000
    assert projection["trajectory"][9]["backlog"] == 8000

def test_redistribution_vertical_spillover():
    engine = RedistributionEngine(restricted_countries={"India"})
    
    # EB1 has 10,000 supply, 5,000 demand -> 5,000 leftover
    # EB2 has 10,000 supply + 5,000 leftover = 15,000 supply. Demand 20,000.
    demands = {
        'EB1': pd.DataFrame({'chargeability': ['UK'], 'count': [5000]}),
        'EB2': pd.DataFrame({'chargeability': ['India'], 'count': [20000]})
    }
    
    # Override limits for test simplicity
    engine.category_weights = {'EB1': 0.5, 'EB2': 0.5, 'EB3': 0}
    results = engine.process_all_categories(demands, total_limit=20000)
    
    assert results['EB1']['allocated'].sum() == 5000
    # EB2 should get its 10,000 + 5,000 from EB1 = 15,000
    assert results['EB2']['allocated'].sum() == 15000

def test_ina_7_percent_bypass():
    engine = RedistributionEngine(restricted_countries={})
    
    # Total supply 10,000. 7% cap is 700.
    # India has 5,000 demand. Others have 0.
    # India should get all 5,000 because visas would otherwise go unused.
    demand_df = pd.DataFrame({'chargeability': ['India'], 'count': [5000]})
    allocated_df, unused = engine.distribute_spillover(demand_df, supply=10000)
    
    assert allocated_df.loc[0, 'allocated'] == 5000
    assert unused == 5000


def test_supply_real_restrictions_increases_india_supply():
    """Real restrictions (actual policy) must increase India EB-1 supply over baseline for accuracy."""
    from src.engine.supply import SupplyCalculator
    from src.constants import DEFAULT_INDIA_EB1_SUPPLY, ACTUAL_RESTRICTED_COUNTRIES
    calc = SupplyCalculator()
    std = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=False)
    real = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=True)
    assert real.india_eb1_supply > std.india_eb1_supply
    assert real.india_eb1_supply >= DEFAULT_INDIA_EB1_SUPPLY
    assert len(ACTUAL_RESTRICTED_COUNTRIES) > 0


def test_predict_accuracy_for_2023_pd_uses_mountain_backlog():
    """For PD 2023-04-01 (near current May 2026 FAD 01APR23), backlog_ahead must use mountain (cutoff filter) not full total.
    This + researched supply makes projections data-driven vs real Visa Bulletin observations."""
    from src.parsers.inventory_parser import InventoryParser
    from src.parsers.pipeline_parser import PipelineParser
    from datetime import datetime
    inv = InventoryParser("data/eb_inventory_january_2026.xlsx")
    pd_dt = datetime(2023, 4, 1)
    inv_ahead = inv.get_india_eb1_queue(cutoff_month=pd_dt.month, cutoff_year=pd_dt.year)
    # The fix ensures mountain (<2023) is used; in data this is 39127 vs total 48162
    assert inv_ahead['mountain'] < inv_ahead['total']
    assert inv_ahead['mountain'] == 39127  # verifiable from Jan 2026 data


@pytest.mark.parametrize("pd_str, apply_real, expected_max_months", [
    ("2023-04-01", False, 80),  # std with researched supply + mountain fix
    ("2023-04-01", True, 25),   # real restrictions boost shortens dramatically
    ("2022-01-01", True, 15),
])
def test_predict_various_pds_and_flags(pd_str, apply_real, expected_max_months):
    """Parametrized coverage for new real flag + mountain logic across PDs (Issue 8)."""
    from src.parsers.inventory_parser import InventoryParser
    from src.parsers.pipeline_parser import PipelineParser
    from src.engine.demand import DemandModeler
    from src.engine.supply import SupplyCalculator
    from datetime import datetime
    pd_dt = datetime.strptime(pd_str, "%Y-%m-%d")
    inv = InventoryParser("data/eb_inventory_january_2026.xlsx")
    inv_stats = inv.get_india_eb1_queue()
    pipe = PipelineParser("data/eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx")
    pipe.load_data()
    pipe_total = pipe.get_india_eb1_backlog()
    total_q = inv_stats['total'] + pipe_total
    if pd_dt.year > 2023:
        frac = min(1.0, ((pd_dt.year - 2024) * 12 + pd_dt.month) / 24.0)
        ba = inv_stats['total'] + int(pipe_total * frac)
    else:
        ba = inv.get_india_eb1_queue(cutoff_month=pd_dt.month, cutoff_year=pd_dt.year)['mountain']
    calc = SupplyCalculator()
    bd = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=apply_real)
    dist = calc.dos_parser.get_monthly_distribution("India", ["E11", "E12", "E13"])
    model = DemandModeler(total_q, bd.india_eb1_supply, dist)
    proj = model.project_clearance(backlog=ba)
    assert proj["months_to_clear"] <= expected_max_months
