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
    for key in ("PERF_API_DELAY_MS", "PERF_API_FAIL_PATHS"):
        monkeypatch.delenv(key, raising=False)
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))

    # Ensure a clean module load for env-sensitive helpers
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
    assert body["perf_api_delay_ms"] == 0
    assert body["perf_api_fail_paths"] == []


def test_delay_middleware_zero_by_default(monkeypatch):
    client, _ = _fresh_client(monkeypatch, PERF_API_DELAY_MS="0")
    t0 = time.perf_counter()
    r = client.get("/api/health")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    # Health is also delay-exempt; should be fast either way
    assert elapsed < 2.0


def test_delay_middleware_applies_to_api_routes(monkeypatch):
    client, _ = _fresh_client(monkeypatch, PERF_API_DELAY_MS="200")
    t0 = time.perf_counter()
    # methodology is relatively light but still goes through middleware delay
    r = client.get("/api/methodology")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200
    assert elapsed_ms >= 180  # allow small scheduling jitter under 200ms target


def test_fail_paths_return_503(monkeypatch):
    client, _ = _fresh_client(
        monkeypatch,
        PERF_API_DELAY_MS="0",
        PERF_API_FAIL_PATHS="/api/waterfall,/api/vb-forecast",
    )
    r = client.get("/api/waterfall")
    assert r.status_code == 503
    assert "PERF_API_FAIL_PATHS" in r.text

    r2 = client.get("/api/methodology")
    assert r2.status_code == 200


def test_health_exempt_from_fail_paths(monkeypatch):
    client, _ = _fresh_client(
        monkeypatch,
        PERF_API_FAIL_PATHS="/api",
    )
    # /api/health must remain reachable for readiness probes
    r = client.get("/api/health")
    assert r.status_code == 200


def test_perf_helpers_parse_env(monkeypatch):
    _, main_mod = _fresh_client(monkeypatch, PERF_API_DELAY_MS="1500", PERF_API_FAIL_PATHS=" /api/a , /api/b ")
    assert main_mod._perf_delay_ms() == 1500
    assert main_mod._perf_fail_prefixes() == ["/api/a", "/api/b"]
