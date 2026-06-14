import pytest
from datetime import date, datetime


def test_vb_predictor_advancement_rates():
    """VBPredictor computes month-over-month FAD advancement correctly."""
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-1")
    rates = p.get_advancement_rates()
    assert len(rates) > 0
    # Each rate should have required keys
    for r in rates:
        assert "bulletin_month" in r
        assert "advancement_days" in r
        assert "fiscal_month" in r
        assert isinstance(r["advancement_days"], int)
        assert 1 <= r["fiscal_month"] <= 12


def test_vb_predictor_seasonal_pattern():
    """Seasonal pattern returns avg advancement per fiscal month."""
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-1")
    seasonal = p.get_seasonal_pattern()
    assert isinstance(seasonal, dict)
    # Should have some fiscal months
    assert len(seasonal) > 0
    # Values are floats (can be negative for retrogression months)
    for fm, avg in seasonal.items():
        assert isinstance(fm, int)
        assert isinstance(avg, float)


def test_vb_predictor_stats():
    """Advancement stats include required fields."""
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-1")
    stats = p.get_advancement_stats()
    assert "recent_avg" in stats
    assert "recent_median" in stats
    assert "recent_stdev" in stats
    assert "overall_avg" in stats
    assert "n_datapoints" in stats
    assert stats["n_datapoints"] > 0


def test_vb_predictor_forecast_basic():
    """Forecast produces correct number of months."""
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-1")
    result = p.forecast(months_ahead=12)
    assert "forecast" in result
    assert len(result["forecast"]) == 12
    assert "latest_actual" in result
    assert "stats" in result
    assert "methodology" in result
    # Each point has required fields
    for pt in result["forecast"]:
        assert "bulletin_month" in pt
        assert "predicted_fad" in pt
        assert "fad_confidence_low" in pt
        assert "fad_confidence_high" in pt


def test_vb_predictor_forecast_with_supply():
    """Supply scaling makes FAD advance faster."""
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-1")
    base = p.forecast(months_ahead=12)
    boosted = p.forecast(months_ahead=12, annual_supply=30000)
    # With higher supply, FAD should advance further
    base_last = base["forecast"][-1]["predicted_fad"]
    boost_last = boosted["forecast"][-1]["predicted_fad"]
    assert boost_last >= base_last  # Further in the future


def test_vb_predictor_forecast_confidence_widens():
    """Confidence bands widen over time."""
    from src.engine.vb_predictor import VBPredictor
    from datetime import date
    p = VBPredictor(category="EB-1")
    result = p.forecast(months_ahead=24)
    if len(result["forecast"]) >= 2:
        first = result["forecast"][0]
        last = result["forecast"][-1]
        first_width = (date.fromisoformat(first["fad_confidence_high"]) -
                       date.fromisoformat(first["fad_confidence_low"])).days
        last_width = (date.fromisoformat(last["fad_confidence_high"]) -
                      date.fromisoformat(last["fad_confidence_low"])).days
        assert last_width >= first_width


def test_vb_predictor_eb2():
    """VBPredictor works for EB-2 category."""
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-2")
    result = p.forecast(months_ahead=6)
    assert len(result["forecast"]) == 6


def test_vb_predictor_eb3():
    """VBPredictor works for EB-3 category."""
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-3")
    result = p.forecast(months_ahead=6)
    assert len(result["forecast"]) == 6


def test_vb_forecast_api_returns_200():
    """API endpoint returns 200 with valid response."""
    from fastapi.testclient import TestClient
    from api.main import app
    client = TestClient(app)
    resp = client.get("/api/vb-forecast?category=EB-1&months_ahead=12")
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "EB-1"
    assert len(data["forecast"]) == 12
    assert "historical" in data
    assert "stats" in data


def test_vb_forecast_api_with_restrictions():
    """API returns different supply_factor with restrictions."""
    from fastapi.testclient import TestClient
    from api.main import app
    client = TestClient(app)
    base = client.get("/api/vb-forecast?category=EB-1&months_ahead=6").json()
    restr = client.get("/api/vb-forecast?category=EB-1&months_ahead=6&apply_real_restrictions=true").json()
    assert restr["supply_factor"] > base["supply_factor"]


# ── OppenheimSolver tests ─────────────────────────────


def test_oppenheim_import():
    """OppenheimSolver imports cleanly."""
    from src.engine.oppenheim import OppenheimSolver, FADPrediction
    assert OppenheimSolver is not None
    assert FADPrediction is not None


def test_oppenheim_calibrate():
    """Calibration computes a materialization rate from current VB + supply."""
    from src.engine.oppenheim import OppenheimSolver
    solver = OppenheimSolver(category="EB-1", apply_real_restrictions=True)
    cal = solver.calibrate()
    assert "calibrated_rate" in cal
    assert "current_fad" in cal
    assert "demand_at_fad" in cal
    assert "annual_supply" in cal
    assert 0 < cal["calibrated_rate"] < 1.0
    assert cal["demand_at_fad"] > 0
    assert cal["annual_supply"] > 0


def test_oppenheim_predict_next_fad():
    """predict_next_fad returns a valid prediction dict."""
    from src.engine.oppenheim import OppenheimSolver
    solver = OppenheimSolver(category="EB-1", apply_real_restrictions=True)
    cal = solver.calibrate()
    solver.materialization_rate = cal["calibrated_rate"]
    pred = solver.predict_next_fad()
    assert "bulletin_month" in pred
    assert "predicted_fad" in pred
    assert "cumulative_demand" in pred
    assert "materialization_rate" in pred
    assert pred["materialization_rate"] == cal["calibrated_rate"]
    # Predicted FAD should be a date string or None (Current)
    if pred["predicted_fad"]:
        date.fromisoformat(pred["predicted_fad"])


def test_oppenheim_predict_trajectory():
    """Trajectory returns correct number of months with required fields."""
    from src.engine.oppenheim import OppenheimSolver
    solver = OppenheimSolver(category="EB-1", apply_real_restrictions=True)
    cal = solver.calibrate()
    solver.materialization_rate = cal["calibrated_rate"]
    traj = solver.predict_trajectory(months_ahead=6)
    assert len(traj) == 6
    for pt in traj:
        assert "bulletin_month" in pt
        assert "predicted_fad" in pt
        assert "fad_low" in pt
        assert "fad_high" in pt
        assert "cumulative_demand" in pt
        assert "fiscal_year" in pt
        assert "remaining_annual_supply" in pt


def test_oppenheim_fad_advances_over_trajectory():
    """FAD should generally advance (or stay Current) over time."""
    from src.engine.oppenheim import OppenheimSolver
    solver = OppenheimSolver(category="EB-1", apply_real_restrictions=True)
    cal = solver.calibrate()
    solver.materialization_rate = cal["calibrated_rate"]
    traj = solver.predict_trajectory(months_ahead=6)
    fads = [pt["predicted_fad"] for pt in traj if pt["predicted_fad"]]
    # Non-Current FADs should be non-decreasing
    for i in range(1, len(fads)):
        assert fads[i] >= fads[i - 1], f"FAD went backwards: {fads[i - 1]} → {fads[i]}"


def test_oppenheim_cumulative_demand():
    """InventoryParser.get_cumulative_demand validates against total."""
    from src.parsers.inventory_parser import InventoryParser
    inv = InventoryParser.latest()
    total_legacy = inv.get_all_eb1_backlogs()["India"]
    total_cumulative = inv.get_cumulative_demand(2099, 1, category="EB1")
    assert total_cumulative == total_legacy


def test_oppenheim_demand_increases_with_cutoff():
    """Cumulative demand should monotonically increase with cutoff date."""
    from src.parsers.inventory_parser import InventoryParser
    inv = InventoryParser.latest()
    prev = 0
    for year in range(2018, 2027):
        d = inv.get_cumulative_demand(year, 1, category="EB1")
        assert d >= prev, f"Demand decreased at {year}: {d} < {prev}"
        prev = d


def test_oppenheim_confidence_bounds():
    """fad_low <= fad_high (low=pessimistic earlier date, high=optimistic later date)."""
    from src.engine.oppenheim import OppenheimSolver
    solver = OppenheimSolver(category="EB-1", apply_real_restrictions=True)
    cal = solver.calibrate()
    solver.materialization_rate = cal["calibrated_rate"]
    pred = solver.predict_next_fad()
    if pred["fad_low"] and pred["fad_high"]:
        low = date.fromisoformat(pred["fad_low"])
        high = date.fromisoformat(pred["fad_high"])
        # fad_low from HIGH rate = earlier/pessimistic date
        # fad_high from LOW rate = later/optimistic date
        assert low <= high, f"Bounds inverted: {low} > {high}"


def test_oppenheim_api_returns_200():
    """The /api/oppenheim endpoint returns 200 with required fields."""
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("starlette not installed")
    from api.main import app
    client = TestClient(app)
    resp = client.get("/api/oppenheim?category=EB-1&months_ahead=6")
    assert resp.status_code == 200
    data = resp.json()
    assert "calibration" in data
    assert "next_fad" in data
    assert "trajectory" in data
    assert len(data["trajectory"]) == 6
    assert data["calibration"]["calibrated_rate"] > 0
