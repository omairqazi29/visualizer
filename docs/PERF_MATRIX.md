# Performance Matrix (Docker)

Reproduce slow or broken frontend pages under controlled conditions: healthy
baseline, CPU throttle, memory pressure, artificial API latency, partial API
outage (`PERF_API_FAIL_PATHS`), and API-down (no silent HTTP fallbacks).

Normal `docker compose up` is **unchanged**. Use the overlay file only when
running the matrix. **`PERF_API_*` is overlay-only** (not in base compose) so
accidental host env cannot inject latency into everyday stacks.

## Quick start

```bash
# Playwright required (Python 3.10–3.12; 3.14 often lacks greenlet wheels)
python3.11 -m pip install playwright==1.49.1
python3.11 -m playwright install chromium

# Default: baseline + api-slow + api-paused
./scripts/run_perf_matrix.sh
# or
python3.11 scripts/perf_matrix.py --scenarios baseline,api-slow,api-paused --page-set heavy

# Include partial-fail / throttle
python3.11 scripts/perf_matrix.py --scenarios baseline,api-slow,api-paused,api-partial-fail
```

**Exit code:** non-zero if **any** assertion fails (including `slower_than_baseline`
and `api_traffic_observed`). No greenwash on comparative checks.

Reports: **`artifacts/perf-matrix/report-latest.md`** (gitignored).

## Scenarios

| Scenario | Project | API port | FE port | Stress |
|---|---|---:|---:|---|
| `baseline` | `perf-baseline` | 18000 | 13000 | Healthy; must observe API XHR |
| `api-slow` | `perf-api-slow` | 18001 | 13001 | `PERF_API_ENABLE=1` + `PERF_API_DELAY_MS=2000` |
| `cpu-throttle` | `perf-cpu-throttle` | 18002 | 13002 | `API_CPUS=0.5` |
| `mem-pressure` | `perf-mem-pressure` | 18003 | 13003 | Low mem limits |
| `api-paused` | `perf-api-paused` | dead 18999 | 13004 | Frontend only |
| `api-partial-fail` | `perf-api-partial-fail` | 18007 | 13007 | Fail expensive `/api/*` prefixes (503) |
| `heavy-pages-only` / `light-pages-only` | … | 18005/6 | 13005/6 | Page subsets |

CPU defaults are **host-safe** (`min(4, nproc-1)` from the runner), not a fixed 8.

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `API_HOST_PORT` / `FRONTEND_HOST_PORT` | base + overlay | Published ports |
| `NEXT_PUBLIC_API_URL` | **build-time** | Baked into Next client; must match `API_HOST_PORT`. Runtime compose `environment:` does **not** retarget the SPA — always `up --build` after URL changes |
| `REQUIRE_API_URL` | build / overlay | Fail fast if URL missing in Docker builds |
| `PERF_API_ENABLE` | **overlay only** | Master gate (`1`/`true`) for delay/fail simulation |
| `PERF_API_DELAY_MS` | overlay | Async per-request delay (capped at 30000 ms) |
| `PERF_API_FAIL_PATHS` | overlay | Comma-separated prefixes under `/api/` → 503 |
| `API_CPUS` / `FRONTEND_CPUS` | overlay | Must be ≤ host CPUs |
| `API_MEM_LIMIT` / `FRONTEND_MEM_LIMIT` | overlay | Memory ceilings |

### Manual stack (always pass NEXT_PUBLIC_API_URL + --build)

```bash
API_HOST_PORT=18001 FRONTEND_HOST_PORT=13001 \
PERF_API_ENABLE=1 PERF_API_DELAY_MS=2000 \
NEXT_PUBLIC_API_URL=http://localhost:18001/api REQUIRE_API_URL=1 \
  docker compose -p perf-api-slow \
    -f docker-compose.yml -f docker-compose.perf-matrix.yml \
    up --build -d api frontend
```

Bind publishes on `0.0.0.0` by default — on shared LANs prefer teardown (default) and avoid `--keep-alive`.

## No silent API fallbacks

`frontend/src/lib/api.ts` refuses multi-host retry. In production / `REQUIRE_API_URL=1`,
missing `NEXT_PUBLIC_API_URL` yields interceptor rejection (no localhost mask).
Local `npm run dev` may use an explicit documented fallback with a console warning.

The metrics runner is **Playwright-only** — no HTTP/urllib fallback that could greenwash results.

## Metrics & assertions

Per page (Playwright):

- Navigation timing: TTFB, DCL, **nav `load_ms` only** (not overwritten by TTM)
- **TTM**: time until successful API XHR **and** domain data landmarks (healthy), or API failures (api-paused)
- Median API resource latency
- API request / success / fail counts (matched to scenario API port)
- Console errors; screenshot on failure

Hard assertions (any FAIL → exit 1):

| Assertion | Scenarios |
|---|---|
| `api_traffic_observed` | expect_api (non-zero XHR on every page) |
| `majority_pages_meaningful` | data landmarks + API success |
| `api_failures_visible` | api-paused |
| `partial_api_failures` | api-partial-fail |
| `slower_than_baseline` | api-slow: median TTM ≥ baseline + **1500 ms** |
| `api_latency_reflects_delay` | api-slow: median API latency ≥ **1500 ms** |

## Teardown

Stacks are torn down in a `finally` block unless `--keep-alive` / `--no-teardown`.
Emergency cleanup:

```bash
for p in baseline api-slow api-paused api-partial-fail; do
  docker compose -p perf-$p -f docker-compose.yml -f docker-compose.perf-matrix.yml down -v
done
```

## Tests

```bash
python3 -m pytest tests/test_perf_controls.py tests/test_perf_matrix_assertions.py tests/test_api_url_policy.py -v
python3 -m pytest tests/ -v   # full non-e2e suite
```

## Files

| Path | Role |
|---|---|
| `docker-compose.perf-matrix.yml` | Overlay + `PERF_API_*` |
| `scripts/perf_matrix.py` | Orchestrator + Playwright metrics |
| `scripts/run_perf_matrix.sh` | Picks Playwright-capable Python |
| `api/main.py` | Gated middleware + `/api/health` |
| `frontend/src/lib/api.ts` | Fail-fast API URL |
| `artifacts/perf-matrix/` | Reports (gitignored) |
