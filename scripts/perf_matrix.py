#!/usr/bin/env python3
"""Docker performance matrix runner for The Spillover Engine frontend.

Starts scenario stacks in parallel (compose project per scenario), waits for
health, collects Playwright navigation / network / console metrics per page,
writes JSON + Markdown under artifacts/perf-matrix/, and tears down stacks.

Operator docs: docs/PERF_MATRIX.md

Examples:
  python3 scripts/perf_matrix.py
  python3 scripts/perf_matrix.py --scenarios baseline,api-slow --keep-alive
  python3 scripts/perf_matrix.py --skip-compose --host-mode \\
      --frontend-url http://127.0.0.1:3000 --api-url http://127.0.0.1:8000 \\
      --scenarios host-check
"""

from __future__ import annotations

import argparse
import json
import os
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

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = [
    str(ROOT / "docker-compose.yml"),
    str(ROOT / "docker-compose.perf-matrix.yml"),
]

# All app routes under frontend/src/app/
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

# Selectors that indicate meaningful content (not just a loading spinner).
# Matched as CSS text-ish via Playwright get_by_text / locator; we use a
# broad "not loading forever" heuristic + key landmark text.
MEANINGFUL_HINTS = {
    "/": ["Predict", "Priority", "Spillover", "EB-1", "India"],
    "/waterfall": ["Waterfall", "EB-1", "spillover", "Supply", "INA"],
    "/supply-demand": ["Supply", "Demand", "EB-1", "India"],
    "/vb-forecast": ["Forecast", "Visa Bulletin", "EB-1", "Final Action"],
    "/predict": ["Predict", "Priority", "current", "final"],
    "/methodology": ["Methodology", "INA", "data", "source", "restriction"],
    "/i485-flow": ["I-485", "receipt", "approval", "pending"],
    "/processing-times": ["Processing", "months", "percentile", "USCIS"],
    "/perm-pipeline": ["PERM", "DOL", "pipeline"],
    "/h1b-demand": ["H-1B", "H1B", "cap", "registration"],
    "/i140-receipts": ["I-140", "receipt", "EB-1", "country"],
    "/oppenheim": ["Oppenheim", "materialization", "EB-1"],
    "/legislation": ["Legislation", "bill", "Congress", "scenario"],
    "/ceac-scheduling": ["CEAC", "NVC", "scheduling", "interview"],
}

# Scenario definitions: ports must not conflict for parallel runs.
SCENARIOS: dict[str, dict[str, Any]] = {
    "baseline": {
        "api_port": 18000,
        "frontend_port": 13000,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "all",
            "API_CPUS": "16.0",
            "API_MEM_LIMIT": "8g",
            "FRONTEND_CPUS": "16.0",
            "FRONTEND_MEM_LIMIT": "8g",
        },
        "page_set": "all",
        "expect_api": True,
    },
    "cpu-throttle": {
        "api_port": 18002,
        "frontend_port": 13002,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "all",
            "API_CPUS": "0.5",
            "API_MEM_LIMIT": "8g",
            "FRONTEND_CPUS": "0.5",
            "FRONTEND_MEM_LIMIT": "8g",
        },
        "page_set": "all",
        "expect_api": True,
    },
    "mem-pressure": {
        "api_port": 18003,
        "frontend_port": 13003,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "all",
            "API_CPUS": "16.0",
            "API_MEM_LIMIT": "256m",
            "FRONTEND_CPUS": "16.0",
            "FRONTEND_MEM_LIMIT": "384m",
        },
        "page_set": "all",
        "expect_api": True,
    },
    "api-slow": {
        "api_port": 18001,
        "frontend_port": 13001,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_DELAY_MS": "2000",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "all",
            "API_CPUS": "16.0",
            "API_MEM_LIMIT": "8g",
            "FRONTEND_CPUS": "16.0",
            "FRONTEND_MEM_LIMIT": "8g",
        },
        "page_set": "all",
        "expect_api": True,
        # Comparative assertion: median page load should exceed baseline by delay budget
        "min_load_delta_vs_baseline_ms": 1500,
    },
    "api-paused": {
        "api_port": 18999,  # unused — API not started
        "frontend_port": 13004,
        "services": ["frontend"],
        "env": {
            # Point browser at a guaranteed-dead API port so failures are honest
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "all",
            "API_CPUS": "16.0",
            "API_MEM_LIMIT": "8g",
            "FRONTEND_CPUS": "16.0",
            "FRONTEND_MEM_LIMIT": "8g",
        },
        "page_set": "heavy",  # enough to see error UX
        "expect_api": False,
        "expect_api_failures": True,
    },
    "heavy-pages-only": {
        "api_port": 18005,
        "frontend_port": 13005,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "heavy",
            "API_CPUS": "16.0",
            "API_MEM_LIMIT": "8g",
            "FRONTEND_CPUS": "16.0",
            "FRONTEND_MEM_LIMIT": "8g",
        },
        "page_set": "heavy",
        "expect_api": True,
    },
    "light-pages-only": {
        "api_port": 18006,
        "frontend_port": 13006,
        "services": ["api", "frontend"],
        "env": {
            "PERF_API_DELAY_MS": "0",
            "PERF_API_FAIL_PATHS": "",
            "PERF_PAGE_SET": "light",
            "API_CPUS": "16.0",
            "API_MEM_LIMIT": "8g",
            "FRONTEND_CPUS": "16.0",
            "FRONTEND_MEM_LIMIT": "8g",
        },
        "page_set": "light",
        "expect_api": True,
    },
    # Host-mode placeholder (no compose) — used with --skip-compose
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
    load_ms: float | None = None
    time_to_meaningful_ms: float | None = None
    api_request_count: int = 0
    api_failed_count: int = 0
    console_errors: list[str] = field(default_factory=list)
    error: str | None = None
    screenshot: str | None = None
    final_url: str | None = None


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
    # Browser on host → published API port. For api-paused, point at dead port.
    if cfg.get("expect_api"):
        env["NEXT_PUBLIC_API_URL"] = f"http://localhost:{api_port}/api"
    else:
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
    # Build frontend so NEXT_PUBLIC_API_URL is correct per scenario ports
    build_cmd = compose_cmd(project, "build", *services)
    try:
        subprocess.run(build_cmd, cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        return False, f"build failed: {e.stderr[-2000:] if e.stderr else e}"

    up_cmd = compose_cmd(project, "up", "-d", "--remove-orphans", *services)
    try:
        subprocess.run(up_cmd, cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        return False, f"up failed: {e.stderr[-2000:] if e.stderr else e}"
    return True, None


def stop_scenario(name: str, cfg: dict[str, Any]) -> None:
    project = f"perf-{name}"
    env = scenario_env(name, cfg)
    cmd = compose_cmd(project, "down", "-v", "--remove-orphans")
    subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)


def wait_http(url: str, timeout_s: float = 180.0, expect_ok: bool = True) -> tuple[bool, str | None]:
    deadline = time.time() + timeout_s
    last_err: str | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                code = getattr(resp, "status", 200)
                if expect_ok and 200 <= int(code) < 500:
                    return True, None
                if not expect_ok:
                    return True, None
                last_err = f"HTTP {code}"
        except Exception as e:  # noqa: BLE001 — health poll
            last_err = str(e)
            if not expect_ok:
                # For negative health (api down), connection error is success
                return True, None
        time.sleep(2)
    return False, last_err or "timeout"


def wait_scenario_health(name: str, cfg: dict[str, Any], timeout_s: float) -> str | None:
    api_port = int(cfg["api_port"])
    fe_port = int(cfg["frontend_port"])
    fe_url = f"http://127.0.0.1:{fe_port}/"
    ok_fe, err_fe = wait_http(fe_url, timeout_s=timeout_s, expect_ok=True)
    if not ok_fe:
        return f"frontend not ready at {fe_url}: {err_fe}"
    if cfg.get("expect_api"):
        api_health = f"http://127.0.0.1:{api_port}/api/health"
        ok_api, err_api = wait_http(api_health, timeout_s=timeout_s, expect_ok=True)
        if not ok_api:
            # Fallback: /docs often works even if health route is old image
            ok_docs, err_docs = wait_http(f"http://127.0.0.1:{api_port}/docs", timeout_s=30, expect_ok=True)
            if not ok_docs:
                return f"api not ready ({api_health}: {err_api}; /docs: {err_docs})"
    return None


def collect_page_metrics(
    browser,
    frontend_url: str,
    path: str,
    api_port: int,
    screenshot_dir: Path,
    scenario: str,
    navigation_timeout_ms: int = 90_000,
) -> PageMetrics:
    from playwright.sync_api import TimeoutError as PWTimeout

    page = browser.new_page()
    console_errors: list[str] = []
    api_reqs = 0
    api_fail = 0
    api_host_token = f":{api_port}"

    def on_console(msg) -> None:
        if msg.type == "error":
            console_errors.append(msg.text[:500])

    def on_response(resp) -> None:
        nonlocal api_reqs, api_fail
        u = resp.url
        if "/api" in u and (api_host_token in u or "localhost" in u or "127.0.0.1" in u):
            api_reqs += 1
            if resp.status >= 400 or resp.status == 0:
                api_fail += 1

    def on_request_failed(req) -> None:
        nonlocal api_fail, api_reqs
        u = req.url
        if "/api" in u:
            api_reqs += 1
            api_fail += 1

    page.on("console", on_console)
    page.on("response", on_response)
    page.on("requestfailed", on_request_failed)

    url = frontend_url.rstrip("/") + path
    t0 = time.perf_counter()
    metrics = PageMetrics(path=path, ok=False, final_url=url)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=navigation_timeout_ms)
        # Prefer full load but don't fail the whole page if long-polling hangs
        try:
            page.wait_for_load_state("load", timeout=min(30_000, navigation_timeout_ms))
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

        # Time to meaningful content: first matching landmark text
        hints = MEANINGFUL_HINTS.get(path, ["Spillover", "EB"])
        meaningful_ms = None
        for hint in hints:
            try:
                loc = page.get_by_text(hint, exact=False).first
                loc.wait_for(state="visible", timeout=15_000)
                meaningful_ms = round((time.perf_counter() - t0) * 1000, 1)
                break
            except Exception:  # noqa: BLE001
                continue
        # Fallback: main landmark or body text length
        if meaningful_ms is None:
            try:
                page.locator("main, body").first.wait_for(state="visible", timeout=5_000)
                text_len = page.evaluate("() => (document.body && document.body.innerText || '').length")
                if text_len and int(text_len) > 80:
                    meaningful_ms = round((time.perf_counter() - t0) * 1000, 1)
            except Exception:  # noqa: BLE001
                pass
        metrics.time_to_meaningful_ms = meaningful_ms
        metrics.api_request_count = api_reqs
        metrics.api_failed_count = api_fail
        metrics.console_errors = console_errors[:20]
        metrics.ok = meaningful_ms is not None
        if not metrics.ok:
            metrics.error = "no meaningful content detected within timeout"
    except Exception as e:  # noqa: BLE001
        metrics.error = str(e)[:800]
        metrics.ok = False
        metrics.api_request_count = api_reqs
        metrics.api_failed_count = api_fail
        metrics.console_errors = console_errors[:20]

    if not metrics.ok:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        safe = path.strip("/").replace("/", "_") or "home"
        shot = screenshot_dir / f"{scenario}_{safe}.png"
        try:
            page.screenshot(path=str(shot), full_page=True)
            metrics.screenshot = str(shot)
        except Exception:  # noqa: BLE001
            pass

    page.close()
    return metrics


def collect_page_metrics_http(
    frontend_url: str,
    path: str,
    api_port: int,
    expect_api: bool,
) -> PageMetrics:
    """Fallback metrics without Playwright (TTFB via HTTP GET only)."""
    url = frontend_url.rstrip("/") + path
    metrics = PageMetrics(path=path, ok=False, final_url=url)
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "perf-matrix/http-fallback"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read(200_000)
            code = getattr(resp, "status", 200)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        metrics.ttfb_ms = round(elapsed_ms, 1)
        metrics.dom_content_loaded_ms = round(elapsed_ms, 1)
        metrics.load_ms = round(elapsed_ms, 1)
        text = body.decode("utf-8", errors="replace")
        hints = MEANINGFUL_HINTS.get(path, ["Spillover"])
        hit = any(h.lower() in text.lower() for h in hints) or len(text) > 500
        metrics.time_to_meaningful_ms = round(elapsed_ms, 1) if hit else None
        metrics.ok = bool(hit) and 200 <= int(code) < 400
        if not metrics.ok:
            metrics.error = f"HTTP {code} or no landmark text in SSR HTML"
        # Probe API health for failure counting when expect_api is False
        api_health = f"http://127.0.0.1:{api_port}/api/health"
        try:
            with urllib.request.urlopen(api_health, timeout=3) as ar:
                metrics.api_request_count = 1
                if getattr(ar, "status", 200) >= 400:
                    metrics.api_failed_count = 1
        except Exception:
            metrics.api_request_count = 1
            metrics.api_failed_count = 1
            if not expect_api:
                # API down is expected — count as visible failure signal
                pass
    except Exception as e:  # noqa: BLE001
        metrics.error = str(e)[:800]
        metrics.api_failed_count = 1
        metrics.api_request_count = 1
    return metrics


def run_browser_suite(
    scenario: str,
    cfg: dict[str, Any],
    frontend_url: str,
    artifact_dir: Path,
    page_set_override: str | None = None,
) -> list[PageMetrics]:
    page_set = page_set_override or cfg.get("page_set") or "all"
    paths = pages_for_set(page_set)
    api_port = int(cfg["api_port"])
    shot_dir = artifact_dir / "screenshots"
    results: list[PageMetrics] = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "WARNING: playwright not installed for this interpreter; "
            "using HTTP fallback metrics (install via python3.11 -m pip install playwright).",
            file=sys.stderr,
        )
        for path in paths:
            results.append(
                collect_page_metrics_http(
                    frontend_url,
                    path,
                    api_port=api_port,
                    expect_api=bool(cfg.get("expect_api", True)),
                )
            )
        return results

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
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def evaluate_assertions(
    results: dict[str, ScenarioResult],
) -> None:
    """Attach comparative assertions (specific deltas, not 'loaded somehow')."""
    baseline = results.get("baseline")
    base_loads: list[float] = []
    if baseline:
        for pm in baseline.pages:
            if pm.load_ms is not None:
                base_loads.append(pm.load_ms)
            elif pm.dom_content_loaded_ms is not None:
                base_loads.append(pm.dom_content_loaded_ms)
    base_med = median(base_loads)

    for name, sr in results.items():
        cfg = SCENARIOS.get(name, {})
        loads: list[float] = []
        for pm in sr.pages:
            if pm.load_ms is not None:
                loads.append(pm.load_ms)
            elif pm.dom_content_loaded_ms is not None:
                loads.append(pm.dom_content_loaded_ms)
        med = median(loads)
        failed_api_pages = sum(1 for pm in sr.pages if pm.api_failed_count > 0)
        ok_pages = sum(1 for pm in sr.pages if pm.ok)

        if cfg.get("expect_api_failures"):
            sr.assertions.append(
                {
                    "name": "api_failures_visible",
                    "pass": failed_api_pages >= max(1, len(sr.pages) // 2),
                    "detail": f"{failed_api_pages}/{len(sr.pages)} pages had API failures "
                    f"(expect majority when API paused / no silent fallback)",
                }
            )
        elif cfg.get("expect_api") and sr.pages:
            sr.assertions.append(
                {
                    "name": "majority_pages_meaningful",
                    "pass": ok_pages >= max(1, int(0.7 * len(sr.pages))),
                    "detail": f"{ok_pages}/{len(sr.pages)} pages reached meaningful content",
                }
            )

        min_delta = cfg.get("min_load_delta_vs_baseline_ms")
        if min_delta is not None and base_med is not None and med is not None:
            delta = med - base_med
            sr.assertions.append(
                {
                    "name": "slower_than_baseline",
                    "pass": delta >= float(min_delta),
                    "detail": (
                        f"median timing {med:.0f}ms vs baseline {base_med:.0f}ms "
                        f"(delta {delta:.0f}ms, need ≥{min_delta}ms)"
                    ),
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

    lines: list[str] = [
        "# Performance Matrix Report",
        "",
        f"Generated (UTC): {payload['generated_at']}",
        "",
        "## Summary",
        "",
        "| Scenario | Pages OK | Median DCL (ms) | Median Load (ms) | Median TTM (ms) | API fails (sum) | Assertions |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, sr in results.items():
        ok_n = sum(1 for p in sr.pages if p.ok)
        dcls = [p.dom_content_loaded_ms for p in sr.pages if p.dom_content_loaded_ms is not None]
        loads = [p.load_ms for p in sr.pages if p.load_ms is not None]
        ttms = [p.time_to_meaningful_ms for p in sr.pages if p.time_to_meaningful_ms is not None]
        api_fails = sum(p.api_failed_count for p in sr.pages)
        asserts = ", ".join(
            ("PASS" if a["pass"] else "FAIL") + f":{a['name']}" for a in sr.assertions
        ) or "—"
        lines.append(
            f"| {name} | {ok_n}/{len(sr.pages)} | "
            f"{median(dcls) or '—'} | {median(loads) or '—'} | {median(ttms) or '—'} | "
            f"{api_fails} | {asserts} |"
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
        lines.append("| Path | OK | TTFB | DCL | Load | TTM | API req | API fail | Errors |")
        lines.append("|---|:---:|---:|---:|---:|---:|---:|---:|---|")
        for p in sr.pages:
            err = (p.error or "")[:60].replace("|", "/")
            lines.append(
                f"| {p.path} | {'yes' if p.ok else 'no'} | "
                f"{p.ttfb_ms or '—'} | {p.dom_content_loaded_ms or '—'} | "
                f"{p.load_ms or '—'} | {p.time_to_meaningful_ms or '—'} | "
                f"{p.api_request_count} | {p.api_failed_count} | {err or '—'} |"
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
            "- **baseline** is the healthy reference path.",
            "- **api-slow** should show higher median timings vs baseline (PERF_API_DELAY_MS).",
            "- **api-paused** should surface API failures (no silent localhost fallback).",
            "- **cpu-throttle** / **mem-pressure** may elevate TTM or error rates under load.",
            "",
            "See `docs/PERF_MATRIX.md` for how to re-run and interpret env vars.",
        ]
    )
    md_path = artifact_dir / f"report-{ts}.md"
    latest_md = artifact_dir / "report-latest.md"
    text = "\n".join(lines) + "\n"
    md_path.write_text(text, encoding="utf-8")
    latest_md.write_text(text, encoding="utf-8")
    return json_path, md_path


def run_one_scenario(
    name: str,
    *,
    skip_compose: bool,
    frontend_url_override: str | None,
    api_url_override: str | None,
    artifact_dir: Path,
    health_timeout: float,
    page_set_override: str | None,
) -> ScenarioResult:
    cfg = SCENARIOS[name]
    project = f"perf-{name}"
    api_port = int(cfg["api_port"])
    fe_port = int(cfg["frontend_port"])
    frontend_url = frontend_url_override or f"http://127.0.0.1:{fe_port}"
    api_url = api_url_override or f"http://127.0.0.1:{api_port}"
    sr = ScenarioResult(
        name=name,
        project=project,
        frontend_url=frontend_url,
        api_url=api_url,
        started=False,
    )

    if not skip_compose and cfg.get("services"):
        ok, err = start_scenario(name, cfg)
        sr.started = ok
        if not ok:
            sr.compose_error = err
            return sr
        health_err = wait_scenario_health(name, cfg, timeout_s=health_timeout)
        if health_err:
            sr.health_error = health_err
            # Still try browser metrics — captures failure UX
    else:
        sr.started = True

    try:
        sr.pages = run_browser_suite(
            name,
            cfg,
            frontend_url,
            artifact_dir,
            page_set_override=page_set_override,
        )
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        sr.health_error = (sr.health_error or "") + f" browser suite error: {e}"
    return sr


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Docker performance matrix with Playwright metrics")
    p.add_argument(
        "--scenarios",
        default="baseline,api-slow,api-paused",
        help="Comma-separated scenario names (default: baseline,api-slow,api-paused)",
    )
    p.add_argument(
        "--all-scenarios",
        action="store_true",
        help="Run all defined scenarios (baseline, cpu-throttle, mem-pressure, api-slow, api-paused, heavy/light)",
    )
    p.add_argument("--skip-compose", action="store_true", help="Do not start/stop compose stacks")
    p.add_argument("--host-mode", action="store_true", help="Alias for metrics against given URLs")
    p.add_argument("--frontend-url", default=None, help="Override frontend base URL (host-mode)")
    p.add_argument("--api-url", default=None, help="Override API base URL (host-mode)")
    p.add_argument("--no-teardown", action="store_true", help="Leave stacks running")
    p.add_argument("--keep-alive", action="store_true", help="Alias for --no-teardown")
    p.add_argument(
        "--artifact-dir",
        default=str(ROOT / "artifacts" / "perf-matrix"),
        help="Output directory for reports",
    )
    p.add_argument("--health-timeout", type=float, default=300.0, help="Seconds to wait for health")
    p.add_argument("--max-parallel", type=int, default=3, help="Max parallel compose stacks")
    p.add_argument("--page-set", default=None, choices=["all", "heavy", "light"], help="Override page set")
    p.add_argument(
        "--sequential-metrics",
        action="store_true",
        help="Run browser metrics one scenario at a time (less CPU contention)",
    )
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
            "heavy-pages-only",
            "light-pages-only",
        ]
    else:
        names = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    for n in names:
        if n not in SCENARIOS:
            print(f"Unknown scenario: {n}. Known: {', '.join(SCENARIOS)}", file=sys.stderr)
            return 2

    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    skip_compose = args.skip_compose or args.host_mode
    no_teardown = args.no_teardown or args.keep_alive

    print(f"Perf matrix scenarios: {names}")
    print(f"Artifacts: {artifact_dir}")

    results: dict[str, ScenarioResult] = {}

    # Phase 1: start stacks in parallel (unless skip)
    if not skip_compose:
        with ThreadPoolExecutor(max_workers=max(1, args.max_parallel)) as pool:
            futs = {
                pool.submit(start_scenario, n, SCENARIOS[n]): n
                for n in names
                if SCENARIOS[n].get("services")
            }
            for fut in as_completed(futs):
                n = futs[fut]
                ok, err = fut.result()
                print(f"  start {n}: {'ok' if ok else 'FAIL'} {err or ''}")
                if not ok:
                    results[n] = ScenarioResult(
                        name=n,
                        project=f"perf-{n}",
                        frontend_url=f"http://127.0.0.1:{SCENARIOS[n]['frontend_port']}",
                        api_url=f"http://127.0.0.1:{SCENARIOS[n]['api_port']}",
                        started=False,
                        compose_error=err,
                    )

        # Health wait (sequential is fine — polls are cheap)
        for n in names:
            if n in results and results[n].compose_error:
                continue
            if not SCENARIOS[n].get("services"):
                continue
            herr = wait_scenario_health(n, SCENARIOS[n], timeout_s=args.health_timeout)
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
                        health_error=herr,
                    ),
                ).health_error = herr
            else:
                print(f"  health {n}: ok")

    # Phase 2: browser metrics (prefer sequential to avoid CPU fight with throttled stacks)
    def _metric_job(n: str) -> ScenarioResult:
        if n in results and results[n].compose_error and not results[n].started:
            return results[n]
        cfg = SCENARIOS[n]
        fe = args.frontend_url or f"http://127.0.0.1:{cfg['frontend_port']}"
        api = args.api_url or f"http://127.0.0.1:{cfg['api_port']}"
        # If we already have a partial result (health warn), reuse shell
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
        except Exception as e:  # noqa: BLE001
            sr.health_error = (sr.health_error or "") + f" browser: {e}"
        return sr

    if args.sequential_metrics or not skip_compose:
        for n in names:
            print(f"  metrics {n} ...")
            results[n] = _metric_job(n)
    else:
        with ThreadPoolExecutor(max_workers=max(1, args.max_parallel)) as pool:
            futs = {pool.submit(_metric_job, n): n for n in names}
            for fut in as_completed(futs):
                n = futs[fut]
                results[n] = fut.result()
                print(f"  metrics {n}: {sum(1 for p in results[n].pages if p.ok)}/{len(results[n].pages)} ok")

    evaluate_assertions(results)
    json_path, md_path = write_reports(results, artifact_dir)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")

    # Phase 3: teardown
    if not skip_compose and not no_teardown:
        for n in names:
            if SCENARIOS[n].get("services"):
                print(f"  teardown {n}")
                stop_scenario(n, SCENARIOS[n])
    elif not skip_compose and no_teardown:
        print("Leaving stacks up (--keep-alive / --no-teardown). Tear down with:")
        for n in names:
            if SCENARIOS[n].get("services"):
                print(
                    f"  docker compose -p perf-{n} -f docker-compose.yml "
                    f"-f docker-compose.perf-matrix.yml down -v"
                )

    # Exit non-zero if any hard assertion failed
    hard_fail = False
    for sr in results.values():
        if sr.compose_error:
            hard_fail = True
        for a in sr.assertions:
            if not a["pass"] and a["name"] in ("api_failures_visible", "majority_pages_meaningful"):
                hard_fail = True
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
