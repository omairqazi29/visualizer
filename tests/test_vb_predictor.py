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
