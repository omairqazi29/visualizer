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
        assert "is_unavailable" in pt
        # Remaining never negative; monthly clamp respects remaining
        assert pt["remaining_annual_supply"] >= 0
        assert pt["target_monthly_supply"] >= 0


def test_oppenheim_remaining_clamp_non_increasing_within_fy():
    """Within a FY, remaining_annual_supply should not increase after issuance."""
    from src.engine.oppenheim import OppenheimSolver
    solver = OppenheimSolver(category="EB-1", apply_real_restrictions=True)
    cal = solver.calibrate()
    solver.materialization_rate = cal.get("calibrated_rate", 0.65)
    traj = solver.predict_trajectory(months_ahead=18)
    by_fy: dict[int, list[int]] = {}
    for pt in traj:
        by_fy.setdefault(pt["fiscal_year"], []).append(pt["remaining_annual_supply"])
    for fy, rem_list in by_fy.items():
        for i in range(1, len(rem_list)):
            assert rem_list[i] <= rem_list[i - 1], (
                f"FY{fy} remaining rose: {rem_list[i - 1]} → {rem_list[i]}"
            )


def test_oppenheim_eb2_unavailable_until_fy_reset():
    """India EB-2 is U in latest VB — stay U until next Oct FY boundary."""
    from src.engine.oppenheim import OppenheimSolver
    solver = OppenheimSolver(category="EB-2", apply_real_restrictions=True)
    state = solver._latest_vb_state()
    if not state.get("fad_unavailable"):
        pytest.skip("EB-2 not currently Unavailable in VB history")
    traj = solver.predict_trajectory(months_ahead=6)
    reopen_y, reopen_m = solver._numbers_reopen_month(state["year"], state["month"])
    reopen_ord = solver._month_ord(reopen_y, reopen_m)
    for pt in traj:
        y, m = map(int, pt["bulletin_month"].split("-"))
        if solver._month_ord(y, m) < reopen_ord:
            assert pt["is_unavailable"] is True
            assert pt["target_monthly_supply"] == 0
            assert pt["is_current"] is False
        else:
            # After reopen, numbers may flow again
            assert pt["is_unavailable"] is False or pt["target_monthly_supply"] >= 0


def test_oppenheim_fad_advances_over_trajectory():
    """FAD should generally advance (or stay Current) over time."""
    from src.engine.oppenheim import OppenheimSolver
    solver = OppenheimSolver(category="EB-1", apply_real_restrictions=True)
    cal = solver.calibrate()
    solver.materialization_rate = cal["calibrated_rate"]
    traj = solver.predict_trajectory(months_ahead=6)
    fads = [pt["predicted_fad"] for pt in traj if pt["predicted_fad"] and not pt.get("is_unavailable")]
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


def test_seasonal_pattern_refuses_small_sample_claims():
    """3 observations per fiscal month cannot support a 12-way decomposition.

    Regression: the pattern used to be a MEAN over all 90 bulletins, including
    the 2015-2018 era of year-long swings, yielding "seasonal" terms of +805
    and -426 days. Blended at 30% and multiplied by the supply factor, that
    made the forecast leap 23 months in a single bulletin.
    """
    from src.engine.vb_predictor import VBPredictor

    p = VBPredictor(category="EB-1")
    pattern = p.get_seasonal_pattern()
    assert len(pattern) == 12
    # Nothing absurd survives, whatever the sample counts turn out to be.
    for fm, val in pattern.items():
        assert abs(val) < 400, f"fiscal month {fm} seasonal {val} is an outlier, not a season"


def test_base_rate_is_robust_to_a_single_outlier_bulletin():
    from statistics import mean
    from src.engine.vb_predictor import VBPredictor

    p = VBPredictor(category="EB-1")
    stats = p.get_advancement_stats()
    raw = [r["advancement_days"] for r in p.get_advancement_rates()]
    window = raw[-stats["base_rate_window"]:]

    assert stats["base_rate_estimator"] == "winsorized_mean_p10_p90"
    # Robust estimate must not exceed the raw mean, which one +323 bulletin drives.
    assert abs(stats["base_rate_days_per_month"]) <= abs(mean(window)) + 1e-6
    # Sanity: this series really is mostly frozen, and the stat should say so.
    assert 0.0 <= stats["zero_movement_share"] <= 1.0


def test_forecast_does_not_leap_years_in_one_bulletin():
    """Guards the runaway the old mean+seasonal+3x-supply stack produced."""
    from datetime import date
    from src.engine.vb_predictor import VBPredictor

    p = VBPredictor(category="EB-1")
    res = p.forecast(months_ahead=12, annual_supply=19182)
    assert res["supply_factor"] <= VBPredictor.MAX_SUPPLY_FACTOR

    prev = date.fromisoformat(res["latest_actual"]["fad"])
    for row in res["forecast"]:
        nxt = date.fromisoformat(row["predicted_fad"])
        assert (nxt - prev).days <= 200, (
            f"{row['bulletin_month']} advanced {(nxt - prev).days} days in one bulletin"
        )
        prev = nxt


def test_forecast_emits_dof_confidence_bands():
    """The DOF used to ship with no uncertainty at all."""
    from datetime import date
    from src.engine.vb_predictor import VBPredictor

    res = VBPredictor(category="EB-1").forecast(months_ahead=6, annual_supply=19182)
    assert res["dof_gap_min_months"] <= res["dof_gap_months"] <= res["dof_gap_max_months"]
    for row in res["forecast"]:
        if row["predicted_dof"] is None:
            continue
        assert row["dof_confidence_low"] and row["dof_confidence_high"]
        lo = date.fromisoformat(row["dof_confidence_low"])
        hi = date.fromisoformat(row["dof_confidence_high"])
        assert lo <= date.fromisoformat(row["predicted_dof"]) <= hi
