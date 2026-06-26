# Performance Matrix (Docker)

Reproduce slow or broken frontend pages under controlled conditions: healthy
baseline, CPU throttle, memory pressure, artificial API latency, and API-down
(no silent HTTP fallbacks).

Normal `docker compose up` is **unchanged**. Use the overlay file only when
running the matrix.

## Quick start

```bash
# Install Playwright once on the host (for host-side runner)
pip3 install playwright==1.49.1
playwright install chromium

# Default: baseline + api-slow + api-paused in parallel compose projects
python3 scripts/perf_matrix.py

# Subset / keep stacks for debugging
python3 scripts/perf_matrix.py --scenarios baseline,api-slow --keep-alive

# Full matrix (more RAM/CPU)
python3 scripts/perf_matrix.py --all-scenarios --max-parallel 2

# Host-only metrics against an already-running stack
python3 scripts/perf_matrix.py --skip-compose --host-mode \
  --frontend-url http://127.0.0.1:3000 \
  --api-url http://127.0.0.1:8000 \
  --scenarios host-check
```

Reports land in **`artifacts/perf-matrix/`**:

- `report-latest.md` / `report-latest.json` — latest run
- `report-<timestamp>.md` / `.json` — historical
- `screenshots/` — captured on page-level failures

## Scenarios

| Scenario | Project name | API port | Frontend port | What it stresses |
|---|---|---:|---:|---|
| `baseline` | `perf-baseline` | 18000 | 13000 | Healthy path |
| `api-slow` | `perf-api-slow` | 18001 | 13001 | `PERF_API_DELAY_MS=2000` |
| `cpu-throttle` | `perf-cpu-throttle` | 18002 | 13002 | `API_CPUS=0.5`, `FRONTEND_CPUS=0.5` |
| `mem-pressure` | `perf-mem-pressure` | 18003 | 13003 | Low `mem_limit` on api/frontend |
| `api-paused` | `perf-api-paused` | *(none)* | 13004 | Frontend only; API URL points at dead port |
| `heavy-pages-only` | `perf-heavy-pages-only` | 18005 | 13005 | Subset: waterfall, vb-forecast, predict, … |
| `light-pages-only` | `perf-light-pages-only` | 18006 | 13006 | Subset: methodology, processing-times, … |

Each scenario is **one compose project** (`-p perf-<name>`) so stacks can run
**in parallel** without port clashes.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `API_HOST_PORT` | `8000` | Host port published for the API |
| `FRONTEND_HOST_PORT` | `3000` | Host port published for the frontend |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api` | **Required** in Docker/production builds (`REQUIRE_API_URL=1`). Browser-reachable API base; no multi-host fallback |
| `REQUIRE_API_URL` | `0` (local compose) / `1` (perf-matrix) | Fail fast if `NEXT_PUBLIC_API_URL` missing |
| `PERF_API_DELAY_MS` | `0` | Sleep before each API response (ms). Health/docs exempt |
| `PERF_API_FAIL_PATHS` | *(empty)* | Comma-separated path prefixes → HTTP 503 (partial outage) |
| `PERF_PAGE_SET` | `all` | Hint: `all` \| `heavy` \| `light` (runner also has `--page-set`) |
| `API_CPUS` / `FRONTEND_CPUS` | `8.0` (≈ no throttle; must be ≤ host CPUs) | CPU quota for throttle scenarios (e.g. `0.5`) |
| `API_MEM_LIMIT` / `FRONTEND_MEM_LIMIT` | `8g` | Memory ceiling (e.g. `256m` / `384m`) |

### Manual stack example

```bash
API_HOST_PORT=18001 FRONTEND_HOST_PORT=13001 \
PERF_API_DELAY_MS=2000 \
NEXT_PUBLIC_API_URL=http://localhost:18001/api \
REQUIRE_API_URL=1 \
  docker compose -p perf-api-slow \
    -f docker-compose.yml -f docker-compose.perf-matrix.yml \
    up --build -d api frontend
```

Tear down:

```bash
docker compose -p perf-api-slow \
  -f docker-compose.yml -f docker-compose.perf-matrix.yml down -v
```

## No silent API fallbacks

`frontend/src/lib/api.ts` **requires** `NEXT_PUBLIC_API_URL` when
`NODE_ENV=production` or `REQUIRE_API_URL=1`. There is **no** alternate host
retry and no silent `localhost` mask in Docker builds. Local `npm run dev`
may use an explicit documented fallback with a console warning only.

This makes **api-paused** measurements honest: network failures and error UI
must appear instead of charts loading forever from a wrong origin.

## Metrics collected (Playwright)

Per page:

- Navigation timing: TTFB, `DOMContentLoaded`, `load`
- Time-to-meaningful-content (first landmark text / non-empty main)
- API request count and failed request count (browser network)
- Console errors
- Screenshot on failure

Assertions are **comparative / specific**, e.g.:

- `api-slow` median timing ≥ baseline + ~1.5s (given 2s injected delay)
- `api-paused` majority of pages show API failures (not silent success)
- healthy scenarios: ≥70% pages reach meaningful content

## Optional in-compose runner

Profile `perf-runner` builds `scripts/perf_runner.Dockerfile` (Chromium +
Playwright) for single-stack verification. Prefer the host script when running
**multiple** projects in parallel (one runner coordinates all ports).

```bash
docker compose -f docker-compose.yml -f docker-compose.perf-matrix.yml \
  --profile perf-runner run --rm perf-runner
```

## Tests

- Unit/API: `tests/test_perf_controls.py` — delay middleware off by default;
  fail-paths return 503; health exempt.
- Default `pytest` excludes live Docker (`pytest.ini` does not mark perf as e2e;
  Docker matrix is script-gated, not CI-default).

```bash
python3 -m pytest tests/ -v
python3 scripts/perf_matrix.py --scenarios baseline,api-slow
```

## Files

| Path | Role |
|---|---|
| `docker-compose.perf-matrix.yml` | Overlay: healthcheck, resource limits, perf env, `perf-runner` profile |
| `scripts/perf_matrix.py` | Parallel orchestrator + Playwright metrics + reports |
| `scripts/perf_runner.Dockerfile` | Optional in-compose browser runner |
| `api/main.py` | `PERF_API_*` middleware + `/api/health` |
| `frontend/src/lib/api.ts` | Fail-fast API URL policy |
| `artifacts/perf-matrix/` | Generated reports (screenshots gitignored) |
