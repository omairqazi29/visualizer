# Data-scan e2e (mock publisher + pickup)

Proves the automated data-scan pipeline works end-to-end **without** live
travel.state.gov / uscis.gov. A Docker mock serves government-style HTML index
pages + minimal xlsx fixtures; the real `src/ingestion` scanner/fetcher runs
against it via opt-in `INGESTION_*` env overrides.

> **Security warning:** Never set `INGESTION_*` in GitHub Actions, production,
> or staging. These overrides redirect scans/downloads and extend the host
> allowlist. Use only for local/e2e mock runs (this harness sets them explicitly).

## Quick start

```bash
# Build + start mock publisher only (profile-gated; normal compose unchanged)
docker compose -f docker-compose.yml -f docker-compose.data-scan-e2e.yml \
  --profile data-scan-e2e up --build -d mock-data-publisher

# Run e2e (starts/stops docker if needed)
./scripts/e2e_data_scan_pickup.sh

# Or pytest directly (mock must already be up)
MOCK_PUBLISHER_URL=http://127.0.0.1:8765 \
  pytest tests/e2e/test_data_scan_pickup.py -m e2e -v -s
```

## In-compose one-shot

```bash
docker compose -f docker-compose.yml -f docker-compose.data-scan-e2e.yml \
  --profile data-scan-e2e run --rm scan-runner
```

## Parallel servers (mock + API, nice-to-have)

The main `api` service lives in `docker-compose.yml` (no profile). You can run
it alongside the mock publisher to exercise multi-server parallelism:

```bash
# Mock (profile) + existing API (always available in base compose)
docker compose -f docker-compose.yml -f docker-compose.data-scan-e2e.yml \
  --profile data-scan-e2e up --build -d mock-data-publisher api

curl -sf http://127.0.0.1:8765/health   # mock
curl -sf http://127.0.0.1:8000/api/health   # api (if route exists)

# Or let the runner script optionally start api:
WITH_API=1 ./scripts/e2e_data_scan_pickup.sh
```

`scan-runner` in the e2e compose file is a one-shot pytest container (depends on
healthy mock); it does not start `api`. Use the commands above when you want
both publishers in parallel.

## Local mock (no Docker)

```bash
python tests/e2e/mock_data_server/server.py   # :8765
SKIP_DOCKER=1 ./scripts/e2e_data_scan_pickup.sh
```

## What it asserts

1. Mock `/health` and DOS/USCIS index HTML are reachable
2. First scan against empty temp `INGESTION_DATA_DIR` sees seed files as `status=new`
3. `POST /publish/new` adds another DOS FSC xlsx
4. Second scan marks **exactly** that file as `status=new` (`pass2_new == [published_name]`) and prior files `status=exists`
5. Fetch writes valid xlsx (`PK` magic) into the isolated data tree
6. `scan_and_pr --scan --dry-run` CLI path works against the mock

## Env overrides (opt-in only; production unchanged)

**Do not set these in GHA/production** — see security warning above.

| Variable | Purpose |
|---|---|
| `INGESTION_PROJECT_ROOT` | Project root for path resolution |
| `INGESTION_DATA_DIR` | Isolated `data/` write target |
| `INGESTION_SOURCE_URL_<source_id>` | Per-source scan URL override |
| `INGESTION_SOURCE_URL_OVERRIDES` | JSON map of source_id → scan_url |
| `INGESTION_EXTRA_ALLOWED_HOSTS` | Extra hosts on every source allowlist |
| `INGESTION_REQUEST_DELAY_SEC` | Polite delay (use `0` for fast e2e) |
| `MOCK_PUBLISHER_URL` | Mock base URL for tests/script |

## Markers

- `@pytest.mark.e2e` — this suite
- `@pytest.mark.integration` — also tagged; default `pytest` excludes both via `addopts`

Default unit suite: `pytest -m 'not integration and not e2e'` (or just `pytest`).
