# Performance Matrix Report

Generated (UTC): 2026-06-26T18:56:41.049825+00:00

## Summary

| Scenario | Pages OK | Median DCL (ms) | Median Load (ms) | Median TTM (ms) | API fails (sum) | Assertions |
|---|---:|---:|---:|---:|---:|---|
| baseline | 14/14 | 35.3 | 102.45 | 143.1 | 0 | PASS:majority_pages_meaningful |
| api-slow | 14/14 | 68.55000000000001 | 145.3 | 176.8 | 0 | PASS:majority_pages_meaningful, FAIL:slower_than_baseline |
| api-paused | 6/6 | 21.450000000000003 | 95.05 | 127.35 | 90 | PASS:api_failures_visible |

## Per-scenario pages

### baseline

- Frontend: http://127.0.0.1:13000
- API: http://127.0.0.1:18000

| Path | OK | TTFB | DCL | Load | TTM | API req | API fail | Errors |
|---|:---:|---:|---:|---:|---:|---:|---:|---|
| / | yes | 47.0 | 129.2 | 164.9 | 213.3 | 0 | 0 | — |
| /waterfall | yes | 23.8 | 58.7 | 122.0 | 151.2 | 0 | 0 | — |
| /supply-demand | yes | 53.7 | 74.0 | 151.8 | 182.6 | 0 | 0 | — |
| /vb-forecast | yes | 4.4 | 19.3 | 103.0 | 133.6 | 0 | 0 | — |
| /predict | yes | 21.7 | 33.9 | 101.9 | 135.0 | 0 | 0 | — |
| /methodology | yes | 11.0 | 38.9 | 78.7 | 109.3 | 0 | 0 | — |
| /i485-flow | yes | 10.5 | 20.0 | 86.3 | 112.6 | 0 | 0 | — |
| /processing-times | yes | 3.9 | 13.3 | 78.7 | 107.6 | 0 | 0 | — |
| /perm-pipeline | yes | 3.7 | 12.1 | 83.3 | 109.4 | 0 | 0 | — |
| /h1b-demand | yes | 7.5 | 15.4 | 88.3 | 116.9 | 0 | 0 | — |
| /i140-receipts | yes | 9.4 | 36.7 | 134.3 | 157.7 | 0 | 0 | — |
| /oppenheim | yes | 3.8 | 13.8 | 94.1 | 45202.3 | 0 | 0 | — |
| /legislation | yes | 109.3 | 196.7 | 314.0 | 353.6 | 0 | 0 | — |
| /ceac-scheduling | yes | 5.6 | 87.9 | 140.5 | 170.9 | 0 | 0 | — |

Assertions:
- **PASS** `majority_pages_meaningful` — 14/14 pages reached meaningful content

### api-slow

- Frontend: http://127.0.0.1:13001
- API: http://127.0.0.1:18001

| Path | OK | TTFB | DCL | Load | TTM | API req | API fail | Errors |
|---|:---:|---:|---:|---:|---:|---:|---:|---|
| / | yes | 45.8 | 111.3 | 209.1 | 247.0 | 0 | 0 | — |
| /waterfall | yes | 80.5 | 107.0 | 174.9 | 202.8 | 0 | 0 | — |
| /supply-demand | yes | 21.6 | 36.6 | 126.8 | 153.9 | 0 | 0 | — |
| /vb-forecast | yes | 6.3 | 46.5 | 108.3 | 139.5 | 0 | 0 | — |
| /predict | yes | 28.7 | 47.2 | 123.2 | 155.8 | 0 | 0 | — |
| /methodology | yes | 9.7 | 57.2 | 88.7 | 128.3 | 0 | 0 | — |
| /i485-flow | yes | 30.0 | 40.9 | 121.8 | 149.6 | 0 | 0 | — |
| /processing-times | yes | 43.9 | 107.5 | 185.1 | 213.0 | 0 | 0 | — |
| /perm-pipeline | yes | 30.4 | 40.6 | 151.0 | 189.5 | 0 | 0 | — |
| /h1b-demand | yes | 87.1 | 118.7 | 285.2 | 320.3 | 0 | 0 | — |
| /i140-receipts | yes | 83.9 | 135.0 | 234.9 | 279.4 | 0 | 0 | — |
| /oppenheim | yes | 48.4 | 540.3 | 742.9 | 45816.6 | 0 | 0 | — |
| /legislation | yes | 47.8 | 79.9 | 139.6 | 164.1 | 0 | 0 | — |
| /ceac-scheduling | yes | 3.8 | 14.2 | 82.8 | 123.4 | 0 | 0 | — |

Assertions:
- **PASS** `majority_pages_meaningful` — 14/14 pages reached meaningful content
- **FAIL** `slower_than_baseline` — median timing 145ms vs baseline 102ms (delta 43ms, need ≥1500ms)

### api-paused

- Frontend: http://127.0.0.1:13004
- API: http://127.0.0.1:18999

| Path | OK | TTFB | DCL | Load | TTM | API req | API fail | Errors |
|---|:---:|---:|---:|---:|---:|---:|---:|---|
| /waterfall | yes | 112.7 | 159.6 | 221.7 | 252.2 | 15 | 15 | — |
| /supply-demand | yes | 86.0 | 124.3 | 183.3 | 214.5 | 15 | 15 | — |
| /vb-forecast | yes | 6.6 | 16.2 | 96.5 | 131.0 | 15 | 15 | — |
| /predict | yes | 4.0 | 13.9 | 66.0 | 100.0 | 15 | 15 | — |
| /oppenheim | yes | 4.5 | 17.1 | 91.9 | 123.7 | 15 | 15 | — |
| /i140-receipts | yes | 17.4 | 25.8 | 93.6 | 119.5 | 15 | 15 | — |

Assertions:
- **PASS** `api_failures_visible` — 6/6 pages had API failures (expect majority when API paused / no silent fallback)

## Comparison notes

- **baseline** is the healthy reference path.
- **api-slow** should show higher median timings vs baseline (PERF_API_DELAY_MS).
- **api-paused** should surface API failures (no silent localhost fallback).
- **cpu-throttle** / **mem-pressure** may elevate TTM or error rates under load.

See `docs/PERF_MATRIX.md` for how to re-run and interpret env vars.
