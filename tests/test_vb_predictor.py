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


# ── Unavailable ("U") resilience ─────────────────────────


@pytest.mark.parametrize("raw,exp_date,exp_status", [
    ("C", None, "C"),
    ("CURRENT", None, "C"),
    ("U", None, "U"),
    ("UNAVAILABLE", None, "U"),
    ("2022-10-15", __import__("datetime").date(2022, 10, 15), "date"),
    ("", None, "C"),
    (None, None, "C"),
    ("bogus", None, "invalid"),
    ("15OCT22", None, "invalid"),
])
def test_normalize_cell(raw, exp_date, exp_status):
    from src.parsers.visa_bulletin_parser import _normalize_cell
    d, s = _normalize_cell(raw)
    assert d == exp_date and s == exp_status


def test_vb_parser_unavailable_status():
    """Jul 2026 EB-2 India FAD is Unavailable — parser must not crash and must flag U."""
    from src.parsers.visa_bulletin_parser import VisaBulletinParser
    vb = VisaBulletinParser(category="EB-2")
    history = vb.get_history()
    assert history, "EB-2 history should be non-empty"
    u_rows = [r for r in history if r.get("fad_unavailable") or r.get("fad_status") == "U"]
    assert u_rows, "Expected at least one Unavailable FAD month (Jul 2026 EB-2)"
    for r in u_rows:
        assert r["fad"] is None
        assert r["fad_status"] == "U"
        assert r["fad_unavailable"] is True


def test_vb_parser_historical_c_status():
    """At least one EB-1 historical Current FAD parses as C with fad is None."""
    from src.parsers.visa_bulletin_parser import VisaBulletinParser
    vb = VisaBulletinParser(category="EB-1")
    c_rows = [r for r in vb.get_history() if r.get("fad_status") == "C"]
    assert c_rows, "EB-1 history includes Current months"
    assert all(r["fad"] is None for r in c_rows)


def test_vb_parser_current_status_unavailable_not_current():
    """When FAD is U, PD is never 'current' and remaining months is null (not 0)."""
    from src.parsers.visa_bulletin_parser import VisaBulletinParser
    vb = VisaBulletinParser(category="EB-2")
    status = vb.get_current_status("2010-01-01", category="EB-2")
    assert status.get("fad_unavailable") is True
    assert status["fad_is_current"] is False
    assert status["current_fad"] is None
    assert status["fad_status"] == "U"
    assert status["fad_remaining_months"] is None


def test_vb_parser_pd_equals_fad_not_current():
    """DOS rule: PD must be earlier than FAD; equality is not current, remaining >= 0.1."""
    from src.parsers.visa_bulletin_parser import VisaBulletinParser
    vb = VisaBulletinParser(category="EB-1")
    status = vb.get_current_status("2022-10-15")  # Jul 2026 FAD
    assert status["fad_is_current"] is False
    assert status["fad_remaining_months"] == 0.1


def test_vb_predictor_eb2_unavailable_forecast_stable():
    """VBPredictor for EB-2 (with U month) returns stable JSON, no exception."""
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-2")
    rates = p.get_advancement_rates()
    for r in rates:
        assert r["fad"] is not None
        assert r["prev_fad"] is not None
    assert not any(r["bulletin_month"] == "2026-07" for r in rates)
    stats = p.get_advancement_stats()
    assert stats["unavailable_months"] >= 1
    result = p.forecast(months_ahead=6)
    la = result["latest_actual"]
    assert la.get("fad_status") == "U"
    assert la.get("fad_unavailable") is True
    assert la.get("fad") is None
    assert la.get("forecast_anchor_fad") == "2013-09-01"
    assert "Unavailable" in result["methodology"]
    assert len(result["forecast"]) == 6
    for pt in result["forecast"]:
        assert pt["predicted_fad"] is not None


def test_vb_predictor_months_until_fad():
    """months_until_fad_reaches returns structured result for a pre-FAD PD."""
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-1")
    early = p.months_until_fad_reaches("2015-01-01")
    assert early.get("already_current") is True or early.get("months_to_current") == 0
    late = p.months_until_fad_reaches("2024-06-01")
    assert "months_to_current" in late
    assert "confidence" in late


def test_months_until_when_fad_unavailable():
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-2")
    early = p.months_until_fad_reaches("2010-01-01")
    assert early.get("already_current") is not True
    assert early.get("category_unavailable") is True
    assert early.get("assumes_numbers_resume") is True
    assert early.get("confidence") == "low"
    assert "months_to_current" in early


def test_vb_predictor_supply_factor_explicit_baseline():
    from src.engine.vb_predictor import VBPredictor
    p = VBPredictor(category="EB-1")
    result = p.forecast(months_ahead=3, annual_supply=20_000, baseline_supply=10_000)
    assert result["supply_factor"] == 2.0


def test_predictor_compare_shared_module():
    from src.engine.predictor_compare import build_predictor_compare
    data = build_predictor_compare("2022-10-01", category="EB-1")
    assert data["demand_months_to_clear"] is not None
    assert data["vb_months_to_current"] is not None


def test_vb_history_api_includes_status():
    """Visa bulletin history exposes fad_status for U months."""
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("starlette not installed")
    from api.main import app
    client = TestClient(app)
    resp = client.get("/api/visa-bulletin-history", params={"category": "EB-2"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] > 0
    u_rows = [r for r in data["history"] if r.get("fad_unavailable") or r.get("fad_status") == "U"]
    assert u_rows, "EB-2 history should include Unavailable FAD row(s)"
    assert u_rows[-1]["fad"] is None


def test_vb_forecast_eb2_api_200():
    """EB-2 forecast (with Unavailable latest FAD) returns 200, not 500."""
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("starlette not installed")
    from api.main import app
    client = TestClient(app)
    resp = client.get("/api/vb-forecast", params={
        "category": "EB-2", "months_ahead": 6, "apply_real_restrictions": "true",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_actual"]["fad_status"] == "U"
    assert data["latest_actual"]["forecast_anchor_fad"] == "2013-09-01"
    assert data["supply_factor"] == 1.0  # no EB-1 restriction boost on EB-2
    assert "forecast" in data
    assert "Unavailable" in data["methodology"]
