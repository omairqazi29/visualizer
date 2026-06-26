"""Unit tests for perf_matrix assertion helpers (no Docker / Playwright)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "perf_matrix.py"


def _load_perf_matrix():
    spec = importlib.util.spec_from_file_location("perf_matrix_mod", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["perf_matrix_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


pm = _load_perf_matrix()


def test_is_api_url_matches_port_and_path():
    assert pm.is_api_url("http://127.0.0.1:18000/api/waterfall", 18000)
    assert pm.is_api_url("http://localhost:18000/api/health", 18000)
    assert not pm.is_api_url("http://127.0.0.1:13000/api/waterfall", 18000)  # frontend port
    assert not pm.is_api_url("http://127.0.0.1:18000/other", 18000)
    assert not pm.is_api_url("http://example.com:18000/api/x", 18000)
    assert not pm.is_api_url("http://api:8000/api/x", 8000)
    assert pm.is_api_url("http://api:8000/api/x", 8000, allow_docker_dns=True)


def test_detect_data_ok_rejects_errors():
    assert not pm.detect_data_ok("Failed to load waterfall data", "/waterfall")
    assert pm.detect_data_ok("Total EB-1 supply and India EB-1 waterfall", "/waterfall")


def test_detect_error_ux():
    assert pm.detect_error_ux("Network Error from axios")
    assert not pm.detect_error_ux("Normal methodology page with INA text")


def test_evaluate_assertions_requires_api_traffic():
    results = {
        "baseline": pm.ScenarioResult(
            name="baseline",
            project="p",
            frontend_url="http://x",
            api_url="http://y",
            started=True,
            pages=[
                pm.PageMetrics(path="/waterfall", ok=True, api_request_count=0),
            ],
        )
    }
    # Patch scenario flags via real SCENARIOS key
    pm.evaluate_assertions(results)
    names = {a["name"]: a["pass"] for a in results["baseline"].assertions}
    assert names.get("api_traffic_observed") is False


def test_evaluate_assertions_slower_than_baseline():
    results = {
        "baseline": pm.ScenarioResult(
            name="baseline",
            project="p",
            frontend_url="http://x",
            api_url="http://y",
            started=True,
            pages=[
                pm.PageMetrics(
                    path="/waterfall",
                    ok=True,
                    api_request_count=2,
                    api_success_count=2,
                    time_to_meaningful_ms=500.0,
                    median_api_latency_ms=100.0,
                ),
            ],
        ),
        "api-slow": pm.ScenarioResult(
            name="api-slow",
            project="p2",
            frontend_url="http://x",
            api_url="http://y",
            started=True,
            pages=[
                pm.PageMetrics(
                    path="/waterfall",
                    ok=True,
                    api_request_count=2,
                    api_success_count=2,
                    time_to_meaningful_ms=600.0,
                    median_api_latency_ms=100.0,  # same latency — fail delta
                ),
            ],
        ),
    }
    pm.evaluate_assertions(results)
    slow_asserts = {a["name"]: a for a in results["api-slow"].assertions}
    assert slow_asserts["slower_than_baseline"]["pass"] is False
    assert slow_asserts["api_latency_reflects_delay"]["pass"] is False

    # Absolute latency high but delta vs baseline still small → slower_than_baseline still fails
    results["api-slow"].pages[0].median_api_latency_ms = 200.0
    results["api-slow"].assertions.clear()
    results["baseline"].assertions.clear()
    pm.evaluate_assertions(results)
    slow_asserts = {a["name"]: a for a in results["api-slow"].assertions}
    assert slow_asserts["slower_than_baseline"]["pass"] is False  # delta 100 < 1500

    results["api-slow"].pages[0].median_api_latency_ms = 2000.0
    results["api-slow"].pages[0].time_to_meaningful_ms = 2500.0
    results["api-slow"].assertions.clear()
    results["baseline"].assertions.clear()
    pm.evaluate_assertions(results)
    slow_asserts = {a["name"]: a for a in results["api-slow"].assertions}
    assert slow_asserts["slower_than_baseline"]["pass"] is True  # delta 1900 >= 1500
    assert slow_asserts["api_latency_reflects_delay"]["pass"] is True


def test_all_fail_pages_cannot_pass_majority_meaningful():
    """Pages with only API failures must not count as OK for expect_api scenarios."""
    results = {
        "baseline": pm.ScenarioResult(
            name="baseline",
            project="p",
            frontend_url="http://x",
            api_url="http://y",
            started=True,
            pages=[
                # Collector would set ok=False; simulate regression if ok were wrongly True
                pm.PageMetrics(
                    path="/supply-demand",
                    ok=False,
                    api_request_count=15,
                    api_success_count=0,
                    api_failed_count=15,
                ),
                pm.PageMetrics(
                    path="/waterfall",
                    ok=True,
                    api_request_count=15,
                    api_success_count=6,
                    api_failed_count=0,
                ),
            ],
        )
    }
    pm.evaluate_assertions(results)
    names = {a["name"]: a for a in results["baseline"].assertions}
    assert names["majority_pages_api_success"]["pass"] is False  # 1/2 < 70%
    assert names["majority_pages_meaningful"]["pass"] is False  # 1/2 ok


def test_api_failures_visible():
    results = {
        "api-paused": pm.ScenarioResult(
            name="api-paused",
            project="p",
            frontend_url="http://x",
            api_url="http://y",
            started=True,
            pages=[
                pm.PageMetrics(path="/waterfall", ok=False, api_request_count=5, api_failed_count=5),
                pm.PageMetrics(path="/predict", ok=False, api_request_count=5, api_failed_count=5),
            ],
        )
    }
    pm.evaluate_assertions(results)
    a = results["api-paused"].assertions[0]
    assert a["name"] == "api_failures_visible"
    assert a["pass"] is True


def test_pages_for_set():
    assert "/waterfall" in pm.pages_for_set("heavy")
    assert "/methodology" in pm.pages_for_set("light")
    assert len(pm.pages_for_set("all")) >= 14


def test_median():
    assert pm.median([1.0, 3.0, 2.0]) == 2.0
    assert pm.median([]) is None
