#!/usr/bin/env python3
"""Docker performance matrix runner — Playwright-only metrics (no HTTP fallback).

See docs/PERF_MATRIX.md.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = [
    str(ROOT / "docker-compose.yml"),
    str(ROOT / "docker-compose.perf-matrix.yml"),
]

ALL_PAGES = [
    "/",
    "/waterfall",
    "/supply-demand",
    "/vb-forecast",
    "/predict",
    "/methodology",
    "/i485-flow",
    "/processing-times",
    "/perm-pipeline",
    "/h1b-demand",
    "/i140-receipts",
    "/oppenheim",
    "/legislation",
    "/ceac-scheduling",
]

HEAVY_PAGES = [
    "/waterfall",
    "/supply-demand",
    "/vb-forecast",
    "/predict",
    "/oppenheim",
    "/i140-receipts",
]

LIGHT_PAGES = [
    "/methodology",
    "/processing-times",
    "/i485-flow",
    "/legislation",
    "/ceac-scheduling",
    "/perm-pipeline",
    "/h1b-demand",
]

# Domain landmarks for *data* success (not sidebar chrome alone). Prefer distinctive phrases.
DATA_HINTS = {
    "/": ["Priority Date", "predict", "India EB"],
    "/waterfall": ["Total EB-1", "India EB-1", "spillover", "140,000", "140000"],
    "/supply-demand": ["Supply", "Demand", "backlog"],
    "/vb-forecast": ["Final Action", "forecast", "Visa Bulletin"],
    "/predict": ["current", "final action", "months"],
    "/methodology": ["INA", "restriction", "data source", "DOS"],
    "/i485-flow": ["I-485", "receipt", "pending"],
    "/processing-times": ["percentile", "months", "USCIS"],
    "/perm-pipeline": ["PERM", "certified", "DOL"],
    "/h1b-demand": ["H-1B", "H1B", "registration"],
    "/i140-receipts": ["I-140", "receipt"],
    "/oppenheim": ["Oppenheim", "materialization"],
    "/legislation": ["bill", "Congress", "scenario"],
    "/ceac-scheduling": ["CEAC", "NVC", "interview"],
}

ERROR_HINTS = [
    "failed to load",
    "network error",
    "econnrefused",
    "next_public_api_url",
    "err_connection",
    "503",
    "axioserror",
]


def _safe_cpus() -> str:
    n = os.cpu_count() or 2
    # Leave headroom; never exceed host (Docker rejects > nproc)
    return f"{max(1.0, min(float(n - 1), 4.0)):.1f}"


SAFE_CPUS = _safe_cpus()

SCENARIOS: dict[str, dict[str, Any]] = {
    "baseline": {
        "api_port": 18000,
        "frontend_port": 13000,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_ENABLE": "1",
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "all",
            "API_CPUS": SAFE_CPUS,
            "API_MEM_LIMIT": "4g",
            "FRONTEND_CPUS": SAFE_CPUS,
            "FRONTEND_MEM_LIMIT": "4g",
        },
        "page_set": "all",
        "expect_api": True,
    },
    "cpu-throttle": {
        "api_port": 18002,
        "frontend_port": 13002,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_ENABLE": "1",
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "API_CPUS": "0.5",
            "API_MEM_LIMIT": "4g",
            "FRONTEND_CPUS": "0.5",
            "FRONTEND_MEM_LIMIT": "4g",
        },
        "page_set": "heavy",
        "expect_api": True,
    },
    "mem-pressure": {
        "api_port": 18003,
        "frontend_port": 13003,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_ENABLE": "1",
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "API_CPUS": SAFE_CPUS,
            "API_MEM_LIMIT": "256m",
            "FRONTEND_CPUS": SAFE_CPUS,
            "FRONTEND_MEM_LIMIT": "384m",
        },
        "page_set": "heavy",
        "expect_api": True,
    },
    "api-slow": {
        "api_port": 18001,
        "frontend_port": 13001,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_ENABLE": "1",
            "PERF_API_DELAY_MS": "2000",
            "PERF_API_FAIL_PATHS": "",
            "API_CPUS": SAFE_CPUS,
            "API_MEM_LIMIT": "4g",
            "FRONTEND_CPUS": SAFE_CPUS,
            "FRONTEND_MEM_LIMIT": "4g",
        },
        "page_set": "all",
        "expect_api": True,
        # Wall-clock TTM / API latency should exceed baseline by ~injected delay
        "min_ttm_delta_vs_baseline_ms": 1500,
        "min_api_latency_ms": 1500,
    },
    "api-paused": {
        "api_port": 18999,
        "frontend_port": 13004,
        "services": ["frontend"],
        "env": {
            "PERF_API_ENABLE": "0",
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "API_CPUS": SAFE_CPUS,
            "API_MEM_LIMIT": "4g",
            "FRONTEND_CPUS": SAFE_CPUS,
            "FRONTEND_MEM_LIMIT": "4g",
        },
        "page_set": "heavy",
        "expect_api": False,
        "expect_api_failures": True,
    },
    "api-partial-fail": {
        "api_port": 18007,
        "frontend_port": 13007,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_ENABLE": "1",
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "/api/waterfall,/api/vb-forecast,/api/supply-demand,/api/oppenheim",
            "API_CPUS": SAFE_CPUS,
            "API_MEM_LIMIT": "4g",
            "FRONTEND_CPUS": SAFE_CPUS,
            "FRONTEND_MEM_LIMIT": "4g",
        },
        "page_set": "heavy",
        "expect_api": True,
        "expect_partial_api_failures": True,
    },
    "heavy-pages-only": {
        "api_port": 18005,
        "frontend_port": 13005,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_ENABLE": "1",
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "heavy",
            "API_CPUS": SAFE_CPUS,
            "API_MEM_LIMIT": "4g",
            "FRONTEND_CPUS": SAFE_CPUS,
            "FRONTEND_MEM_LIMIT": "4g",
        },
        "page_set": "heavy",
        "expect_api": True,
    },
    "light-pages-only": {
        "api_port": 18006,
        "frontend_port": 13006,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_ENABLE": "1",
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "light",
            "API_CPUS": SAFE_CPUS,
            "API_MEM_LIMIT": "4g",
            "FRONTEND_CPUS": SAFE_CPUS,
            "FRONTEND_MEM_LIMIT": "4g",
        },
        "page_set": "light",
        "expect_api": True,
    },
    "in-compose": {
        "api_port": 8000,
        "frontend_port": 3000,
        "services": [],
        "env": {},
        "page_set": "all",
        "expect_api": True,
    },
    "host-check": {
        "api_port": 8000,
        "frontend_port": 3000,
        "services": [],
        "env": {},
        "page_set": "all",
        "expect_api": True,
    },
}


@dataclass
class PageMetrics:
    path: str
    ok: bool
    ttfb_ms: float | None = None
    dom_content_loaded_ms: float | None = None
    load_ms: float | None = None  # navigation timing only (never overwritten with TTM)
    time_to_meaningful_ms: float | None = None
    median_api_latency_ms: float | None = None
    api_request_count: int = 0
    api_success_count: int = 0
    api_failed_count: int = 0
    console_errors: list[str] = field(default_factory=list)
    error: str | None = None
    screenshot: str | None = None
    final_url: str | None = None
    sample_api_urls: list[str] = field(default_factory=list)
    timed_out_ttm: bool = False


@dataclass
class ScenarioResult:
    name: str
    project: str
    frontend_url: str
    api_url: str
    started: bool
    pages: list[PageMetrics] = field(default_factory=list)
    compose_error: str | None = None
    health_error: str | None = None
    assertions: list[dict[str, Any]] = field(default_factory=list)


def pages_for_set(page_set: str) -> list[str]:
    ps = (page_set or "all").lower()
    if ps == "heavy":
        return list(HEAVY_PAGES)
    if ps == "light":
        return list(LIGHT_PAGES)
    return list(ALL_PAGES)


def api_base_url(api_port: int) -> str:
    return f"http://127.0.0.1:{api_port}/api"


def is_api_url(url: str, api_port: int) -> bool:
    """True if URL targets the scenario API origin (host Playwright → published port)."""
    try:
        p = urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        return False
    port = p.port
    if port is None:
        port = 443 if (p.scheme or "") == "https" else 80
    if int(port) != int(api_port):
        return False
    path = p.path or ""
    return path == "/api" or path.startswith("/api/")


def compose_cmd(project: str, *args: str) -> list[str]:
    cmd = ["docker", "compose", "-p", project]
    for f in COMPOSE_FILES:
        cmd.extend(["-f", f])
    cmd.extend(args)
    return cmd


def scenario_env(name: str, cfg: dict[str, Any]) -> dict[str, str]:
    api_port = int(cfg["api_port"])
    fe_port = int(cfg["frontend_port"])
    env = os.environ.copy()
    env.update({k: str(v) for k, v in cfg.get("env", {}).items()})
    env["API_HOST_PORT"] = str(api_port)
    env["FRONTEND_HOST_PORT"] = str(fe_port)
    # Must match published API port (rebuild required — baked into Next client)
    env["NEXT_PUBLIC_API_URL"] = f"http://localhost:{api_port}/api"
    env["REQUIRE_API_URL"] = "1"
    env["COMPOSE_PROJECT_NAME"] = f"perf-{name}"
    return env


def start_scenario(name: str, cfg: dict[str, Any]) -> tuple[bool, str | None]:
    project = f"perf-{name}"
    services = cfg.get("services") or []
    if not services:
        return True, None
    env = scenario_env(name, cfg)
    log_dir = ROOT / "artifacts" / "perf-matrix" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    build_cmd = compose_cmd(project, "build", *services)
    try:
        r = subprocess.run(build_cmd, cwd=ROOT, env=env, check=False, capture_output=True, text=True)
        (log_dir / f"{name}-build.log").write_text((r.stdout or "") + "\n" + (r.stderr or ""), encoding="utf-8")
        if r.returncode != 0:
            return False, f"build failed: {(r.stderr or r.stdout or '')[-2500:]}"
    except OSError as e:
        return False, f"build failed: {e}"

    up_cmd = compose_cmd(project, "up", "-d", "--remove-orphans", *services)
    try:
        r = subprocess.run(up_cmd, cwd=ROOT, env=env, check=False, capture_output=True, text=True)
        (log_dir / f"{name}-up.log").write_text((r.stdout or "") + "\n" + (r.stderr or ""), encoding="utf-8")
        if r.returncode != 0:
            return False, f"up failed: {(r.stderr or r.stdout or '')[-2500:]}"
    except OSError as e:
        return False, f"up failed: {e}"
    return True, None


def stop_scenario(name: str, cfg: dict[str, Any]) -> bool:
    project = f"perf-{name}"
    env = scenario_env(name, cfg)
    cmd = compose_cmd(project, "down", "-v", "--remove-orphans")
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  teardown {name} warn: {(r.stderr or r.stdout or '')[-500:]}", file=sys.stderr)
        return False
    return True


def wait_http(url: str, timeout_s: float = 180.0, expect_ok: bool = True) -> tuple[bool, str | None]:
    deadline = time.time() + timeout_s
    last_err: str | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                code = int(getattr(resp, "status", 200))
                if expect_ok and 200 <= code < 400:
                    return True, None
                if not expect_ok:
                    return True, None
                last_err = f"HTTP {code}"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = str(e)
            if not expect_ok:
                return True, None
        time.sleep(2)
    return False, last_err or "timeout"


def wait_scenario_health(name: str, cfg: dict[str, Any], timeout_s: float, strict_health: bool = True) -> str | None:
    api_port = int(cfg["api_port"])
    fe_port = int(cfg["frontend_port"])
    fe_url = f"http://127.0.0.1:{fe_port}/"
    ok_fe, err_fe = wait_http(fe_url, timeout_s=timeout_s, expect_ok=True)
    if not ok_fe:
        return f"frontend not ready at {fe_url}: {err_fe}"
    if cfg.get("expect_api") and "api" in (cfg.get("services") or []):
        api_health = f"http://127.0.0.1:{api_port}/api/health"
        ok_api, err_api = wait_http(api_health, timeout_s=timeout_s, expect_ok=True)
        if not ok_api:
            if strict_health:
                return f"api /api/health not ready ({api_health}: {err_api}); rebuild api image"
            ok_docs, err_docs = wait_http(f"http://127.0.0.1:{api_port}/docs", timeout_s=30, expect_ok=True)
            if not ok_docs:
                return f"api not ready ({api_health}: {err_api}; /docs: {err_docs})"
        else:
            # Confirm delay config visible for api-slow style scenarios
            try:
                with urllib.request.urlopen(api_health, timeout=5) as resp:
                    body = json.loads(resp.read().decode())
                want_delay = int(cfg.get("env", {}).get("PERF_API_DELAY_MS") or 0)
                if want_delay and int(body.get("perf_api_delay_ms") or 0) != want_delay:
                    return (
                        f"health reports perf_api_delay_ms={body.get('perf_api_delay_ms')} "
                        f"expected {want_delay} (PERF_API_ENABLE / rebuild?)"
                    )
            except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
                return f"health JSON parse failed: {e}"
    return None


def detect_data_ok(text: str, path: str) -> bool:
    """Domain data / chart landmarks — not mere shell or error chrome."""
    lower = (text or "").lower()
    if any(e in lower for e in ERROR_HINTS):
        return False
    hints = DATA_HINTS.get(path, ["spillover", "eb-1"])
    return any(h.lower() in lower for h in hints)


def detect_error_ux(text: str) -> bool:
    lower = (text or "").lower()
    return any(e in lower for e in ERROR_HINTS)


def collect_page_metrics(
    browser,
    frontend_url: str,
    path: str,
    api_port: int,
    screenshot_dir: Path,
    scenario: str,
    expect_api: bool,
    expect_api_failures: bool,
    navigation_timeout_ms: int = 90_000,
) -> PageMetrics:
    """Collect page metrics with a single authoritative API outcome map (no double-count)."""
    from playwright.sync_api import TimeoutError as PWTimeout

    context = browser.new_context()
    page = context.new_page()
    console_errors: list[str] = []
    # key = method|url → {"status": "pending"|"ok"|"fail", "latency_ms": float|None}
    outcomes: dict[str, dict[str, Any]] = {}
    sample_urls: list[str] = []

    def _key(method: str, url: str) -> str:
        return f"{method}|{url}"

    def on_console(msg) -> None:
        if msg.type == "error":
            console_errors.append(msg.text[:500])

    def on_request(req) -> None:
        u = req.url
        if not is_api_url(u, api_port):
            return
        k = _key(req.method, u)
        if k not in outcomes:
            outcomes[k] = {"status": "pending", "latency_ms": None}
            if len(sample_urls) < 5:
                sample_urls.append(u[:200])

    def on_response(resp) -> None:
        u = resp.url
        if not is_api_url(u, api_port):
            return
        k = _key(resp.request.method, u)
        lat = None
        try:
            timing = resp.request.timing or {}
            te = float(timing.get("responseEnd") or 0)
            ts = float(timing.get("requestStart") or 0)
            if te and ts and te >= ts:
                lat = te - ts
            elif te > 0:
                lat = te
        except Exception:
            pass
        st = int(resp.status or 0)
        # Response is authoritative: overwrite pending/fail from aborted twins
        if 200 <= st < 400:
            outcomes[k] = {"status": "ok", "latency_ms": lat}
        else:
            outcomes[k] = {"status": "fail", "latency_ms": lat}

    def on_request_failed(req) -> None:
        u = req.url
        if not is_api_url(u, api_port):
            return
        k = _key(req.method, u)
        cur = outcomes.get(k)
        # Do not overwrite a successful or failed HTTP response
        if cur and cur.get("status") in ("ok", "fail"):
            return
        outcomes[k] = {"status": "fail", "latency_ms": None}
        if len(sample_urls) < 5 and u[:200] not in sample_urls:
            sample_urls.append(u[:200])

    def tally() -> tuple[int, int, int, list[float]]:
        reqs = len(outcomes)
        ok_n = sum(1 for v in outcomes.values() if v.get("status") == "ok")
        fail_n = sum(1 for v in outcomes.values() if v.get("status") == "fail")
        lats = [
            float(v["latency_ms"])
            for v in outcomes.values()
            if v.get("status") == "ok" and v.get("latency_ms") is not None
        ]
        return reqs, ok_n, fail_n, lats

    page.on("console", on_console)
    page.on("request", on_request)
    page.on("response", on_response)
    page.on("requestfailed", on_request_failed)

    url = frontend_url.rstrip("/") + path
    t0 = time.perf_counter()
    metrics = PageMetrics(path=path, ok=False, final_url=url)
    api_reqs = api_ok = api_fail = 0

    try:
        # Capture first successful API response during navigation when possible
        try:
            with page.expect_response(
                lambda r: is_api_url(r.url, api_port) and 200 <= int(r.status or 0) < 400,
                timeout=30_000,
            ):
                page.goto(url, wait_until="domcontentloaded", timeout=navigation_timeout_ms)
        except PWTimeout:
            page.goto(url, wait_until="domcontentloaded", timeout=navigation_timeout_ms)
        try:
            page.wait_for_load_state("load", timeout=min(20_000, navigation_timeout_ms))
        except PWTimeout:
            pass

        timing = page.evaluate(
            """() => {
              const n = performance.getEntriesByType('navigation')[0];
              if (!n) return null;
              return {
                ttfb: n.responseStart,
                dcl: n.domContentLoadedEventEnd,
                load: n.loadEventEnd,
              };
            }"""
        )
        if timing:
            metrics.ttfb_ms = round(float(timing.get("ttfb") or 0), 1)
            metrics.dom_content_loaded_ms = round(float(timing.get("dcl") or 0), 1)
            load_v = float(timing.get("load") or 0)
            metrics.load_ms = round(load_v, 1) if load_v > 0 else None

        # Poll until success criteria or deadline (no networkidle — avoids 12–30s plateaus)
        deadline = time.perf_counter() + 35.0
        data_ok = False
        error_ux = False
        body_text = ""
        settled = False
        while time.perf_counter() < deadline:
            api_reqs, api_ok, api_fail, _lats = tally()
            try:
                body_text = page.evaluate("() => (document.body && document.body.innerText) || ''") or ""
            except Exception:
                body_text = ""
            error_ux = detect_error_ux(body_text)
            data_ok = detect_data_ok(body_text, path)
            content_ok = data_ok or (len(body_text) > 200 and not error_ux)

            if expect_api_failures:
                # Failures only — do not require success
                if api_fail > 0 and api_reqs > 0:
                    metrics.time_to_meaningful_ms = round((time.perf_counter() - t0) * 1000, 1)
                    settled = True
                    break
            elif expect_api:
                # Healthy path: need at least one HTTP 2xx API response + content
                if api_ok > 0 and content_ok and not error_ux:
                    metrics.time_to_meaningful_ms = round((time.perf_counter() - t0) * 1000, 1)
                    settled = True
                    break
            else:
                if content_ok:
                    metrics.time_to_meaningful_ms = round((time.perf_counter() - t0) * 1000, 1)
                    settled = True
                    break
            page.wait_for_timeout(150)

        if not settled:
            metrics.timed_out_ttm = True
            metrics.time_to_meaningful_ms = round((time.perf_counter() - t0) * 1000, 1)

        api_reqs, api_ok, api_fail, api_latencies = tally()
        metrics.api_request_count = api_reqs
        metrics.api_success_count = api_ok
        metrics.api_failed_count = api_fail
        metrics.sample_api_urls = sample_urls
        metrics.console_errors = console_errors[:20]
        if api_latencies:
            metrics.median_api_latency_ms = median([float(x) for x in api_latencies])

        content_ok = data_ok or (len(body_text) > 200 and not error_ux)

        if expect_api_failures:
            metrics.ok = api_fail > 0 and api_reqs > 0
            # Failure scenario is not "content success"
            if not metrics.ok:
                metrics.error = "expected API failures not observed"
        elif expect_api:
            # STRICT: success count must be > 0 — failures alone never mark page OK
            metrics.ok = api_ok > 0 and content_ok and not error_ux
            if api_reqs == 0:
                metrics.error = "no API XHR observed (check NEXT_PUBLIC_API_URL bake)"
                metrics.ok = False
            elif api_ok == 0:
                metrics.error = (
                    f"no successful API responses (fail={api_fail}, req={api_reqs}); "
                    "page did not receive live backend data"
                )
                metrics.ok = False
            elif error_ux:
                metrics.error = "error UX visible on healthy scenario"
                metrics.ok = False
            elif not content_ok:
                metrics.error = "no domain data landmarks (shell only?)"
                metrics.ok = False
            elif metrics.timed_out_ttm and api_ok == 0:
                metrics.ok = False
                metrics.error = "TTM timed out without successful API"
        else:
            metrics.ok = bool(data_ok)
    except Exception as e:
        metrics.error = str(e)[:800]
        metrics.ok = False
        api_reqs, api_ok, api_fail, _ = tally()
        metrics.api_request_count = api_reqs
        metrics.api_success_count = api_ok
        metrics.api_failed_count = api_fail
        metrics.console_errors = console_errors[:20]
        metrics.sample_api_urls = sample_urls

    if not metrics.ok:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        safe = path.strip("/").replace("/", "_") or "home"
        shot = screenshot_dir / f"{scenario}_{safe}.png"
        try:
            page.screenshot(path=str(shot), full_page=True)
            metrics.screenshot = str(shot)
        except Exception:
            pass

    context.close()
    return metrics


def run_browser_suite(
    scenario: str,
    cfg: dict[str, Any],
    frontend_url: str,
    artifact_dir: Path,
    page_set_override: str | None = None,
) -> list[PageMetrics]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise SystemExit(
            "Playwright is required (no HTTP fallback). "
            "Use Python 3.10–3.12 and: pip install playwright && playwright install chromium\n"
            f"Import error: {e}"
        ) from e

    page_set = page_set_override or cfg.get("page_set") or "all"
    paths = pages_for_set(page_set)
    api_port = int(cfg["api_port"])
    shot_dir = artifact_dir / "screenshots"
    expect_api = bool(cfg.get("expect_api"))
    expect_fail = bool(cfg.get("expect_api_failures"))
    results: list[PageMetrics] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for path in paths:
                results.append(
                    collect_page_metrics(
                        browser,
                        frontend_url,
                        path,
                        api_port=api_port,
                        screenshot_dir=shot_dir,
                        scenario=scenario,
                        expect_api=expect_api,
                        expect_api_failures=expect_fail,
                    )
                )
        finally:
            browser.close()
    return results


def median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    if n % 2:
        return round(s[mid], 1)
    return round((s[mid - 1] + s[mid]) / 2.0, 1)


def evaluate_assertions(results: dict[str, ScenarioResult]) -> None:
    baseline = results.get("baseline")
    base_ttms: list[float] = []
    base_api_lat: list[float] = []
    if baseline:
        for pm in baseline.pages:
            if pm.time_to_meaningful_ms is not None and not pm.timed_out_ttm:
                base_ttms.append(pm.time_to_meaningful_ms)
            elif pm.time_to_meaningful_ms is not None:
                base_ttms.append(pm.time_to_meaningful_ms)
            if pm.median_api_latency_ms is not None:
                base_api_lat.append(pm.median_api_latency_ms)
    base_ttm_med = median(base_ttms)
    base_api_med = median(base_api_lat)

    for name, sr in results.items():
        cfg = SCENARIOS.get(name, {})
        ttms = [p.time_to_meaningful_ms for p in sr.pages if p.time_to_meaningful_ms is not None]
        api_lats = [p.median_api_latency_ms for p in sr.pages if p.median_api_latency_ms is not None]
        ttm_med = median(ttms)
        api_med = median(api_lats)
        failed_api_pages = sum(1 for pm in sr.pages if pm.api_failed_count > 0)
        ok_pages = sum(1 for pm in sr.pages if pm.ok)
        total_api = sum(pm.api_request_count for pm in sr.pages)

        if cfg.get("expect_api") and sr.pages and not cfg.get("expect_api_failures"):
            pages_with_success = sum(1 for pm in sr.pages if pm.api_success_count > 0)
            sr.assertions.append(
                {
                    "name": "api_traffic_observed",
                    "pass": total_api > 0 and all(pm.api_request_count > 0 for pm in sr.pages),
                    "detail": f"total API req={total_api}; pages with traffic="
                    f"{sum(1 for p in sr.pages if p.api_request_count > 0)}/{len(sr.pages)}",
                }
            )
            n_pages = len(sr.pages)
            success_ratio = pages_with_success / n_pages if n_pages else 0.0
            ok_ratio = ok_pages / n_pages if n_pages else 0.0
            sr.assertions.append(
                {
                    "name": "majority_pages_api_success",
                    "pass": success_ratio >= 0.7,
                    "detail": f"{pages_with_success}/{n_pages} pages have api_success_count > 0 (need ≥70%)",
                }
            )
            # ok_pages already requires api_success_count > 0 in collector for expect_api
            sr.assertions.append(
                {
                    "name": "majority_pages_meaningful",
                    "pass": ok_ratio >= 0.7,
                    "detail": f"{ok_pages}/{n_pages} pages OK (requires api_success_count>0 + content, need ≥70%)",
                }
            )

        if cfg.get("expect_api_failures"):
            sr.assertions.append(
                {
                    "name": "api_failures_visible",
                    "pass": failed_api_pages >= max(1, len(sr.pages) // 2) and total_api > 0,
                    "detail": f"{failed_api_pages}/{len(sr.pages)} pages had API failures "
                    f"(total_api={total_api}; no silent fallback)",
                }
            )

        if cfg.get("expect_partial_api_failures"):
            sr.assertions.append(
                {
                    "name": "partial_api_failures",
                    "pass": failed_api_pages >= 1 and total_api > 0,
                    "detail": f"pages with API fails={failed_api_pages}, total_api={total_api}",
                }
            )

        min_delta = cfg.get("min_ttm_delta_vs_baseline_ms")
        if min_delta is not None:
            # Prefer API latency **delta vs baseline** (not absolute alone)
            use_api = base_api_med is not None and api_med is not None
            if use_api:
                delta = api_med - base_api_med
                sr.assertions.append(
                    {
                        "name": "slower_than_baseline",
                        "pass": delta >= float(min_delta),
                        "detail": (
                            f"median API lat {api_med:.1f}ms vs baseline {base_api_med:.1f}ms "
                            f"(delta {delta:.1f}ms, need ≥{min_delta}ms)"
                        ),
                    }
                )
            elif base_ttm_med is None or ttm_med is None:
                sr.assertions.append(
                    {
                        "name": "slower_than_baseline",
                        "pass": False,
                        "detail": "missing baseline/scenario TTM and API latency medians",
                    }
                )
            else:
                delta = ttm_med - base_ttm_med
                sr.assertions.append(
                    {
                        "name": "slower_than_baseline",
                        "pass": delta >= float(min_delta),
                        "detail": (
                            f"median TTM {ttm_med:.1f}ms vs baseline {base_ttm_med:.1f}ms "
                            f"(delta {delta:.1f}ms, need ≥{min_delta}ms)"
                        ),
                    }
                )

        min_api = cfg.get("min_api_latency_ms")
        if min_api is not None:
            # Absolute floor still useful when delay is injected (must be slow in absolute terms)
            if api_med is None:
                sr.assertions.append(
                    {
                        "name": "api_latency_reflects_delay",
                        "pass": False,
                        "detail": "no median API latency observed on successful responses",
                    }
                )
            else:
                sr.assertions.append(
                    {
                        "name": "api_latency_reflects_delay",
                        "pass": api_med >= float(min_api),
                        "detail": f"median API latency {api_med:.1f}ms on successes (need ≥{min_api}ms)",
                    }
                )


def write_reports(results: dict[str, ScenarioResult], artifact_dir: Path) -> tuple[Path, Path]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": {k: asdict(v) for k, v in results.items()},
    }
    json_path = artifact_dir / f"report-{ts}.json"
    latest_json = artifact_dir / "report-latest.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def fmt(v: float | None) -> str:
        return f"{v:.1f}" if v is not None else "—"

    lines: list[str] = [
        "# Performance Matrix Report",
        "",
        f"Generated (UTC): {payload['generated_at']}",
        "",
        "## Summary",
        "",
        "| Scenario | Pages OK | Median DCL | Median Nav Load | Median TTM | Median API lat | API req | API fail | Assertions |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, sr in results.items():
        ok_n = sum(1 for p in sr.pages if p.ok)
        dcls = [p.dom_content_loaded_ms for p in sr.pages if p.dom_content_loaded_ms is not None]
        loads = [p.load_ms for p in sr.pages if p.load_ms is not None]
        ttms = [p.time_to_meaningful_ms for p in sr.pages if p.time_to_meaningful_ms is not None]
        alats = [p.median_api_latency_ms for p in sr.pages if p.median_api_latency_ms is not None]
        api_reqs = sum(p.api_request_count for p in sr.pages)
        api_fails = sum(p.api_failed_count for p in sr.pages)
        asserts = ", ".join(
            ("PASS" if a["pass"] else "FAIL") + f":{a['name']}" for a in sr.assertions
        ) or "—"
        lines.append(
            f"| {name} | {ok_n}/{len(sr.pages)} | "
            f"{fmt(median(dcls))} | {fmt(median(loads))} | {fmt(median(ttms))} | "
            f"{fmt(median(alats))} | {api_reqs} | {api_fails} | {asserts} |"
        )

    lines.extend(["", "## Per-scenario pages", ""])
    for name, sr in results.items():
        lines.append(f"### {name}")
        lines.append("")
        if sr.compose_error:
            lines.append(f"- Compose error: `{sr.compose_error}`")
        if sr.health_error:
            lines.append(f"- Health error: `{sr.health_error}`")
        lines.append(f"- Frontend: {sr.frontend_url}")
        lines.append(f"- API: {sr.api_url}")
        lines.append("")
        lines.append(
            "| Path | OK | TTFB | DCL | NavLoad | TTM | API lat | API req | API ok | API fail | Errors |"
        )
        lines.append("|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for p in sr.pages:
            err = (p.error or "")[:60].replace("|", "/")
            lines.append(
                f"| {p.path} | {'yes' if p.ok else 'no'} | "
                f"{fmt(p.ttfb_ms)} | {fmt(p.dom_content_loaded_ms)} | "
                f"{fmt(p.load_ms)} | {fmt(p.time_to_meaningful_ms)} | "
                f"{fmt(p.median_api_latency_ms)} | "
                f"{p.api_request_count} | {p.api_success_count} | {p.api_failed_count} | {err or '—'} |"
            )
        if sr.assertions:
            lines.append("")
            lines.append("Assertions:")
            for a in sr.assertions:
                flag = "PASS" if a["pass"] else "FAIL"
                lines.append(f"- **{flag}** `{a['name']}` — {a['detail']}")
        lines.append("")

    lines.extend(
        [
            "## Comparison notes",
            "",
            "- **baseline** is the healthy reference (API traffic required).",
            "- **api-slow** must show higher median TTM and API latency vs baseline (`PERF_API_DELAY_MS=2000`, threshold ≥1.5s).",
            "- **api-paused** must surface API failures (no silent localhost fallback).",
            "- Navigation `load_ms` is **not** overwritten by TTM.",
            "",
            "Any assertion FAIL makes the process exit non-zero.",
            "",
            "See `docs/PERF_MATRIX.md`.",
        ]
    )
    md_path = artifact_dir / f"report-{ts}.md"
    latest_md = artifact_dir / "report-latest.md"
    text = "\n".join(lines) + "\n"
    md_path.write_text(text, encoding="utf-8")
    latest_md.write_text(text, encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Docker performance matrix with Playwright metrics")
    p.add_argument(
        "--scenarios",
        default="baseline,api-slow,api-paused",
        help="Comma-separated scenario names",
    )
    p.add_argument(
        "--all-scenarios",
        action="store_true",
        help="Run all compose-backed scenarios including partial-fail / throttle",
    )
    p.add_argument("--skip-compose", action="store_true", help="Do not start/stop compose stacks")
    p.add_argument("--host-mode", action="store_true", help="Metrics against given URLs only")
    p.add_argument("--frontend-url", default=None)
    p.add_argument("--api-url", default=None)
    p.add_argument("--no-teardown", action="store_true")
    p.add_argument("--keep-alive", action="store_true")
    p.add_argument(
        "--artifact-dir",
        default=str(ROOT / "artifacts" / "perf-matrix"),
    )
    p.add_argument("--health-timeout", type=float, default=300.0)
    p.add_argument(
        "--max-parallel",
        type=int,
        default=1,
        help="Parallel compose builds/starts (default 1 for stable timings)",
    )
    p.add_argument("--page-set", default=None, choices=["all", "heavy", "light"])
    p.add_argument("--sequential-metrics", action="store_true", default=True)
    p.add_argument("--allow-legacy-api", action="store_true", help="Allow /docs health fallback")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.all_scenarios:
        names = [
            "baseline",
            "cpu-throttle",
            "mem-pressure",
            "api-slow",
            "api-paused",
            "api-partial-fail",
            "heavy-pages-only",
            "light-pages-only",
        ]
    else:
        names = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    for n in names:
        if n not in SCENARIOS:
            print(f"Unknown scenario: {n}. Known: {', '.join(SCENARIOS)}", file=sys.stderr)
            return 2
        if not args.skip_compose and not args.host_mode:
            if not SCENARIOS[n].get("services") and n not in ("in-compose", "host-check"):
                print(f"Scenario {n} has no compose services; use --skip-compose", file=sys.stderr)
                return 2

    # Fail fast if Playwright missing
    try:
        import playwright  # noqa: F401
    except ImportError:
        print(
            "ERROR: Playwright required. Install on Python 3.10–3.12:\n"
            "  python3.11 -m pip install playwright && python3.11 -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    skip_compose = args.skip_compose or args.host_mode
    no_teardown = args.no_teardown or args.keep_alive
    results: dict[str, ScenarioResult] = {}
    started_names: list[str] = []

    print(f"Perf matrix scenarios: {names}")
    print(f"Artifacts: {artifact_dir}")
    print(f"Safe CPU default: {SAFE_CPUS}")

    try:
        if not skip_compose:
            # Sequential build/start by default (max_parallel=1); optional parallel
            def _start(n: str) -> tuple[str, bool, str | None]:
                ok, err = start_scenario(n, SCENARIOS[n])
                return n, ok, err

            with ThreadPoolExecutor(max_workers=max(1, args.max_parallel)) as pool:
                futs = [pool.submit(_start, n) for n in names if SCENARIOS[n].get("services")]
                for fut in as_completed(futs):
                    n, ok, err = fut.result()
                    print(f"  start {n}: {'ok' if ok else 'FAIL'} {err or ''}")
                    if ok:
                        started_names.append(n)
                    else:
                        results[n] = ScenarioResult(
                            name=n,
                            project=f"perf-{n}",
                            frontend_url=f"http://127.0.0.1:{SCENARIOS[n]['frontend_port']}",
                            api_url=f"http://127.0.0.1:{SCENARIOS[n]['api_port']}",
                            started=False,
                            compose_error=err,
                        )

            for n in names:
                if n in results and results[n].compose_error:
                    continue
                if not SCENARIOS[n].get("services"):
                    continue
                if n not in started_names:
                    continue
                herr = wait_scenario_health(
                    n,
                    SCENARIOS[n],
                    timeout_s=args.health_timeout,
                    strict_health=not args.allow_legacy_api,
                )
                if herr:
                    print(f"  health {n}: WARN {herr}")
                    results.setdefault(
                        n,
                        ScenarioResult(
                            name=n,
                            project=f"perf-{n}",
                            frontend_url=f"http://127.0.0.1:{SCENARIOS[n]['frontend_port']}",
                            api_url=f"http://127.0.0.1:{SCENARIOS[n]['api_port']}",
                            started=True,
                        ),
                    ).health_error = herr
                else:
                    print(f"  health {n}: ok")

        def _metric_job(n: str) -> ScenarioResult:
            if n in results and results[n].compose_error and not results[n].started:
                return results[n]
            cfg = SCENARIOS[n]
            fe = args.frontend_url or f"http://127.0.0.1:{cfg['frontend_port']}"
            api = args.api_url or f"http://127.0.0.1:{cfg['api_port']}"
            existing = results.get(n)
            sr = existing or ScenarioResult(
                name=n,
                project=f"perf-{n}",
                frontend_url=fe,
                api_url=api,
                started=True,
            )
            sr.frontend_url = fe
            sr.api_url = api
            try:
                sr.pages = run_browser_suite(
                    n,
                    cfg,
                    fe,
                    artifact_dir,
                    page_set_override=args.page_set,
                )
            except SystemExit:
                raise
            except Exception as e:
                sr.health_error = (sr.health_error or "") + f" browser: {e}"
            return sr

        for n in names:
            print(f"  metrics {n} ...")
            results[n] = _metric_job(n)
            print(
                f"    -> {sum(1 for p in results[n].pages if p.ok)}/{len(results[n].pages)} ok, "
                f"api_req={sum(p.api_request_count for p in results[n].pages)}"
            )

        evaluate_assertions(results)
        json_path, md_path = write_reports(results, artifact_dir)
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
    finally:
        if not skip_compose and not no_teardown:
            for n in names:
                if SCENARIOS[n].get("services"):
                    print(f"  teardown {n}")
                    stop_scenario(n, SCENARIOS[n])
        elif not skip_compose and no_teardown:
            print("Leaving stacks up (--keep-alive). Tear down with:")
            for n in names:
                if SCENARIOS[n].get("services"):
                    print(
                        f"  docker compose -p perf-{n} -f docker-compose.yml "
                        f"-f docker-compose.perf-matrix.yml down -v"
                    )

    hard_fail = False
    for sr in results.values():
        if sr.compose_error:
            hard_fail = True
            print(f"COMPOSE FAIL [{sr.name}]: {sr.compose_error}", file=sys.stderr)
        if sr.health_error:
            hard_fail = True
            print(f"HEALTH FAIL [{sr.name}]: {sr.health_error}", file=sys.stderr)
        for a in sr.assertions:
            if not a["pass"]:
                hard_fail = True
                print(f"ASSERT FAIL [{sr.name}] {a['name']}: {a['detail']}", file=sys.stderr)
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
