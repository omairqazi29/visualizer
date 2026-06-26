"""Tests for opt-in PERF_API_* simulation controls (no live Docker required)."""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("starlette", minversion="0.0")

try:
    from fastapi.testclient import TestClient
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT))
except Exception:
    pytest.skip("TestClient import path unavailable", allow_module_level=True)


def _fresh_client(monkeypatch, **env):
    """Re-import api.main with env overrides so middleware reads current values."""
    for key in (
        "PERF_API_ENABLE",
        "PERF_API_DELAY_MS",
        "PERF_API_FAIL_PATHS",
    ):
        monkeypatch.delenv(key, raising=False)
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))

    for mod in list(sys.modules):
        if mod == "api.main" or mod.startswith("api.main."):
            del sys.modules[mod]

    import api.main as main_mod

    return TestClient(main_mod.app), main_mod


def test_health_endpoint_default(monkeypatch):
    client, _ = _fresh_client(monkeypatch)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["perf_api_enable"] is False
    assert body["perf_api_delay_ms"] == 0
    assert body["perf_api_fail_paths"] == []


def test_delay_disabled_without_enable_flag(monkeypatch):
    """PERF_API_DELAY_MS alone must not inject delay unless PERF_API_ENABLE=1."""
    client, _ = _fresh_client(monkeypatch, PERF_API_DELAY_MS="5000")
    t0 = time.perf_counter()
    r = client.get("/api/methodology")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 1.0


def test_health_not_delayed_when_enable_and_delay(monkeypatch):
    client, _ = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_DELAY_MS="200",
    )
    t0 = time.perf_counter()
    r = client.get("/api/health")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200
    assert r.json()["perf_api_delay_ms"] == 200
    assert r.json()["perf_api_enable"] is True
    assert elapsed_ms < 100


def test_delay_middleware_applies_to_api_routes(monkeypatch):
    client, _ = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_DELAY_MS="200",
    )
    t0 = time.perf_counter()
    r = client.get("/api/methodology")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200
    assert elapsed_ms >= 180
    assert elapsed_ms < 5000


def test_delay_capped(monkeypatch):
    _, main_mod = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_DELAY_MS="999999",
    )
    assert main_mod._perf_delay_ms() == 30_000


def test_invalid_delay_env(monkeypatch):
    _, main_mod = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_DELAY_MS="abc",
    )
    assert main_mod._perf_delay_ms() == 0


def test_fail_paths_return_503(monkeypatch):
    client, _ = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_DELAY_MS="0",
        PERF_API_FAIL_PATHS="/api/waterfall,/api/vb-forecast",
    )
    r = client.get("/api/waterfall")
    assert r.status_code == 503
    assert "PERF_API_FAIL_PATHS" in r.text

    r2 = client.get("/api/methodology")
    assert r2.status_code == 200


def test_fail_path_short_circuits_before_delay(monkeypatch):
    client, _ = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_DELAY_MS="2000",
        PERF_API_FAIL_PATHS="/api/waterfall",
    )
    t0 = time.perf_counter()
    r = client.get("/api/waterfall")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 503
    assert elapsed < 0.5


def test_health_exempt_from_fail_paths(monkeypatch):
    client, _ = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_FAIL_PATHS="/api",
    )
    r = client.get("/api/health")
    assert r.status_code == 200


def test_docs_exempt_from_fail_paths(monkeypatch):
    client, _ = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_FAIL_PATHS="/api",
    )
    r = client.get("/docs")
    assert r.status_code == 200


def test_fail_prefix_rejects_non_api(monkeypatch):
    _, main_mod = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_FAIL_PATHS="/evil,/api/waterfall",
    )
    assert main_mod._perf_fail_prefixes() == ["/api/waterfall"]


def test_path_matches_fail_prefix_segment_aware(monkeypatch):
    _, main_mod = _fresh_client(monkeypatch, PERF_API_ENABLE="1")
    assert main_mod._path_matches_fail_prefix("/api/waterfall", "/api/waterfall")
    assert main_mod._path_matches_fail_prefix("/api/waterfall/extra", "/api/waterfall")
    # typo prefix /api/w should NOT match /api/waterfall with segment-aware rules
    assert not main_mod._path_matches_fail_prefix("/api/waterfall", "/api/w")


def test_perf_helpers_parse_env(monkeypatch):
    _, main_mod = _fresh_client(
        monkeypatch,
        PERF_API_ENABLE="1",
        PERF_API_DELAY_MS="1500",
        PERF_API_FAIL_PATHS=" /api/a , /api/b ",
    )
    assert main_mod._perf_delay_ms() == 1500
    assert main_mod._perf_fail_prefixes() == ["/api/a", "/api/b"]
