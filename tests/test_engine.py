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
    # inflow_rate=0 to isolate the FY-reset mechanic from inflow behavior.
    dist = {m: 1 / 12 for m in range(1, 13)}
    modeler = DemandModeler(
        inventory_total=15000,
        annual_supply=12000,
        monthly_distribution=dist,
        inflow_rate=0,
    )

    start_date = datetime(2025, 7, 1)
    projection = modeler.project_clearance(start_date=start_date)

    # Oct 1 2025 is index 3 (July=0, Aug=1, Sept=2, Oct=3)
    # Check if Oct reset happened by looking at backlog change
    oct_backlog = projection["trajectory"][3]["backlog"]  # End of Sept
    nov_backlog = projection["trajectory"][4]["backlog"]  # End of Oct

    # Should have cleared 1000 in October
    assert oct_backlog - nov_backlog == 1000


def test_demand_modeler_exhaustion():
    # Annual supply 12,000. Backlog 20,000.
    # Force exhaustion by putting 100% in month 1 (Jan)
    # inflow_rate=0 to isolate the exhaustion mechanic.
    dist = {m: 0 for m in range(1, 13)}
    dist[1] = 1.0

    modeler = DemandModeler(
        inventory_total=20000,
        annual_supply=12000,
        monthly_distribution=dist,
        inflow_rate=0,
    )
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
        "EB1": pd.DataFrame({"chargeability": ["UK"], "count": [5000]}),
        "EB2": pd.DataFrame({"chargeability": ["India"], "count": [20000]}),
    }

    # Override limits for test simplicity
    engine.category_weights = {"EB1": 0.5, "EB2": 0.5, "EB3": 0}
    results = engine.process_all_categories(demands, total_limit=20000)

    assert results["EB1"]["allocated"].sum() == 5000
    # EB2 should get its 10,000 + 5,000 from EB1 = 15,000
    assert results["EB2"]["allocated"].sum() == 15000


def test_ina_7_percent_bypass():
    engine = RedistributionEngine(restricted_countries={})

    # Total supply 10,000. 7% cap is 700.
    # India has 5,000 demand. Others have 0.
    # India should get all 5,000 because visas would otherwise go unused.
    demand_df = pd.DataFrame({"chargeability": ["India"], "count": [5000]})
    allocated_df, unused = engine.distribute_spillover(demand_df, supply=10000)

    assert allocated_df.loc[0, "allocated"] == 5000
    assert unused == 5000


def test_demand_modeler_inflow_increases_backlog():
    """With default inflow, backlog should grow when supply < inflow."""
    dist = {m: 1 / 12 for m in range(1, 13)}
    # Supply 6000/yr = 500/mo. Default inflow ~1210/mo. Net growth ~710/mo.
    modeler = DemandModeler(
        inventory_total=10000, annual_supply=6000, monthly_distribution=dist
    )
    # Default: int(550 * 2.2) = 1210
    assert modeler.monthly_inflow == 1210
    projection = modeler.project_clearance(
        start_date=datetime(2025, 10, 1), backlog=10000
    )
    # After 1 month, backlog should be higher than start (inflow > supply)
    assert projection["trajectory"][1]["backlog"] > 10000


def test_demand_modeler_custom_inflow():
    """Custom inflow_rate computes correctly with DEPENDENT_MULTIPLIER."""
    dist = {m: 1 / 12 for m in range(1, 13)}
    modeler = DemandModeler(
        inventory_total=10000,
        annual_supply=6000,
        monthly_distribution=dist,
        inflow_rate=300,
    )
    # int(300 * 2.2) = 660
    assert modeler.monthly_inflow == 660


def test_demand_modeler_negative_inflow_raises():
    """Negative inflow_rate should raise ValueError."""
    dist = {m: 1 / 12 for m in range(1, 13)}
    with pytest.raises(ValueError, match="non-negative"):
        DemandModeler(
            inventory_total=10000,
            annual_supply=6000,
            monthly_distribution=dist,
            inflow_rate=-100,
        )


def test_demand_modeler_zero_inflow():
    """With inflow_rate=0, no new cases added (old behavior)."""
    dist = {m: 1 / 12 for m in range(1, 13)}
    modeler = DemandModeler(
        inventory_total=10000,
        annual_supply=12000,
        monthly_distribution=dist,
        inflow_rate=0,
    )
    assert modeler.monthly_inflow == 0
    projection = modeler.project_clearance(
        start_date=datetime(2025, 10, 1), backlog=10000
    )
    # Backlog should strictly decrease
    assert projection["trajectory"][1]["backlog"] < 10000


@pytest.mark.parametrize(
    "start_month",
    [1, 4, 7, 9],
)
def test_demand_modeler_mid_fy_proration(start_month):
    """Mid-FY starts must take longer than October start with front-loaded distribution."""
    # Front-loaded distribution: 30% in Oct, rest spread — proration matters
    dist = {m: 0.07 / 11 for m in range(1, 13)}
    dist[10] = 0.30  # October gets 30% of annual supply
    # Normalize
    total = sum(dist.values())
    dist = {m: v / total for m, v in dist.items()}
    modeler = DemandModeler(
        inventory_total=8000,
        annual_supply=12000,
        monthly_distribution=dist,
        inflow_rate=0,
    )
    proj_mid = modeler.project_clearance(
        start_date=datetime(2025, start_month, 1), backlog=8000
    )
    proj_oct = modeler.project_clearance(start_date=datetime(2025, 10, 1), backlog=8000)
    # Mid-FY start misses the big October allocation → takes strictly longer
    assert proj_mid["months_to_clear"] > proj_oct["months_to_clear"]


def test_demand_modeler_sub_threshold_clearance():
    """Backlog below 0.001 threshold should be clamped to zero (clearance)."""
    # Supply exactly equals backlog — after deduction, remainder should be ~0
    dist = {m: 0 for m in range(1, 13)}
    dist[10] = 1.0  # all supply in October
    modeler = DemandModeler(
        inventory_total=1000,
        annual_supply=1000,
        monthly_distribution=dist,
        inflow_rate=0,
    )
    proj = modeler.project_clearance(start_date=datetime(2025, 10, 1), backlog=1000)
    assert proj["cleared"] is True
    assert proj["trajectory"][-1]["backlog"] == 0


def test_demand_modeler_october_start_no_proration():
    """October start should have zero proration (full FY available)."""
    dist = {m: 1 / 12 for m in range(1, 13)}
    modeler = DemandModeler(
        inventory_total=5000,
        annual_supply=12000,
        monthly_distribution=dist,
        inflow_rate=0,
    )
    proj = modeler.project_clearance(start_date=datetime(2025, 10, 1), backlog=5000)
    assert proj["cleared"] is True
    assert proj["months_to_clear"] == 5  # 5000 / 1000-per-month = 5


@pytest.mark.parametrize(
    "month, year, expected_fy",
    [
        (1, 2026, 2026),  # Jan → FY2026 (ends Sep 2026, 8 months away)
        (6, 2026, 2026),  # Jun → FY2026 (ends Sep 2026, 3 months away)
        (7, 2026, 2027),  # Jul → FY2027 (current FY ends <3 months away)
        (9, 2026, 2027),  # Sep → FY2027 (current FY ends this month)
        (10, 2026, 2027),  # Oct → FY2027 (new FY just started)
        (12, 2026, 2027),  # Dec → FY2027
    ],
)
def test_demand_modeler_dynamic_target_fy(month, year, expected_fy):
    """default_target_fy returns correct FY with injectable clock for determinism."""
    assert DemandModeler.default_target_fy(now=datetime(year, month, 15)) == expected_fy


def test_demand_modeler_confidence_uses_dynamic_fy():
    """calculate_confidence_score with target_fy=None uses dynamic default; verify bounded range."""
    dist = {m: 1 / 12 for m in range(1, 13)}
    modeler = DemandModeler(
        inventory_total=10000,
        annual_supply=12000,
        monthly_distribution=dist,
        inflow_rate=0,
    )
    # With 5000 backlog and 12000/yr supply (no inflow), clears in ~5 months.
    # Dynamic target FY end is at least 3 months away, so clearance likely before target.
    score = modeler.calculate_confidence_score(datetime(2023, 1, 1), backlog_ahead=5000)
    assert 0.10 <= score <= 0.98
    # Very large backlog that won't clear → low confidence
    score_low = modeler.calculate_confidence_score(
        datetime(2023, 1, 1), backlog_ahead=500000
    )
    assert score_low == 0.10
    # Score for easy case should be higher than hard case
    assert score > score_low


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
    This + researched supply makes projections data-driven vs real Visa Bulletin observations.
    """
    from src.parsers.inventory_parser import InventoryParser
    from datetime import datetime

    inv = InventoryParser("data/eb_inventory_january_2026.xlsx")
    pd_dt = datetime(2023, 4, 1)
    inv_ahead = inv.get_india_eb1_queue(
        cutoff_month=pd_dt.month, cutoff_year=pd_dt.year
    )
    # The fix ensures mountain (<2023) is used; in data this is 39127 vs total 48162
    assert inv_ahead["mountain"] < inv_ahead["total"]
    assert inv_ahead["mountain"] == 39127  # verifiable from Jan 2026 data


def test_predict_standard_never_clears_with_inflow():
    """Standard supply (6952/yr) < inflow (14520/yr) → backlog never clears."""
    from src.parsers.inventory_parser import InventoryParser
    from src.parsers.pipeline_parser import PipelineParser
    from src.engine.demand import DemandModeler
    from src.engine.supply import SupplyCalculator

    inv = InventoryParser("data/eb_inventory_january_2026.xlsx")
    inv_stats = inv.get_india_eb1_queue()
    pipe = PipelineParser("data/eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx")
    pipe.load_data()
    pipe_total = pipe.get_india_eb1_backlog()
    total_q = inv_stats["total"] + pipe_total
    ba = inv.get_india_eb1_queue(cutoff_month=4, cutoff_year=2023)["mountain"]
    calc = SupplyCalculator()
    bd = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=False)
    dist = calc.dos_parser.get_monthly_distribution("India", ["E11", "E12", "E13"])
    model = DemandModeler(total_q, bd.india_eb1_supply, dist)
    proj = model.project_clearance(backlog=ba)
    assert proj["months_to_clear"] == 600
    assert proj["cleared"] is False
    assert proj["trajectory"][-1]["backlog"] > ba


@pytest.mark.parametrize(
    "pd_str, apply_real",
    [
        # Real restrictions boost supply enough to outpace inflow → clears
        ("2023-04-01", True),
        ("2022-01-01", True),
    ],
)
def test_predict_real_restrictions_with_inflow(pd_str, apply_real):
    """Real restrictions boost supply above inflow → backlog clears within reasonable time."""
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
    total_q = inv_stats["total"] + pipe_total
    ba = inv.get_india_eb1_queue(cutoff_month=pd_dt.month, cutoff_year=pd_dt.year)[
        "mountain"
    ]
    calc = SupplyCalculator()
    bd = calc.get_supply_breakdown(
        apply_freeze=False, apply_real_restrictions=apply_real
    )
    dist = calc.dos_parser.get_monthly_distribution("India", ["E11", "E12", "E13"])
    model = DemandModeler(total_q, bd.india_eb1_supply, dist)
    proj = model.project_clearance(backlog=ba)
    # Real restrictions provide enough supply to clear even with inflow
    assert proj["cleared"] is True
    assert proj["months_to_clear"] < 600
    assert proj["months_to_clear"] > 0


@pytest.mark.parametrize(
    "pd_str, expected_max_months_no_inflow",
    [
        ("2023-04-01", 80),  # std with researched supply + mountain fix (no inflow)
        ("2022-01-01", 80),  # earlier PD, smaller backlog
    ],
)
def test_predict_no_inflow_clearance(pd_str, expected_max_months_no_inflow):
    """Validates clearance timelines with inflow_rate=0 (old behavior, depletion-only)."""
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
    total_q = inv_stats["total"] + pipe_total
    ba = inv.get_india_eb1_queue(cutoff_month=pd_dt.month, cutoff_year=pd_dt.year)[
        "mountain"
    ]
    calc = SupplyCalculator()
    bd = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=False)
    dist = calc.dos_parser.get_monthly_distribution("India", ["E11", "E12", "E13"])
    model = DemandModeler(total_q, bd.india_eb1_supply, dist, inflow_rate=0)
    proj = model.project_clearance(backlog=ba)
    assert proj["months_to_clear"] <= expected_max_months_no_inflow
    assert proj["cleared"] is True
