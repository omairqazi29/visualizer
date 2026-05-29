# Golden Reference Tests

## Purpose

Golden reference tests protect **INA math model fidelity** against the
reference 2026-05-28 data corpus.  They ensure that refactoring, DI
migration, and policy strategy extraction do not silently change the
numerical output of the spillover engine.

## Reference Values (2026-05-28 Corpus)

| Scenario          | india_eb1_supply | eb1_supply | total_eb_supply |
|-------------------|----------------:|----------:|----------------:|
| Standard          |           6,952 |    53,362 |         186,582 |
| Freeze (75-country) |        78,837 |    85,695 |         285,397 |
| Real Restrictions |          31,053 |    53,362 |         186,582 |

Queue total ≈ 93,464 (inventory 48,162 + pipeline 45,302).

## Workflow

### Capture (initial or after intentional changes)

```bash
python -m tests.golden.capture_and_verify --capture
```

Writes JSON files to `tests/golden/references/`:
- `supply_breakdown.json` — full snapshot (all scenarios + parser metadata)
- `waterfall_standard.json` — standard scenario only
- `waterfall_freeze.json` — freeze scenario only
- `waterfall_real_restrictions.json` — real restrictions scenario only

### Verify (CI and local)

```bash
python -m tests.golden.capture_and_verify --verify
```

Loads references, re-runs the engine, asserts:
- **Exact match** on all integer fields
- **Float tolerance 1e-9** on any floating-point values

### Regenerate (dev-only, intentional model updates)

```bash
python -m tests.golden.capture_and_verify --regenerate
```

Alias for `--capture`.  Use **only** after intentional changes to INA math
(new constants, new policy logic, etc.).  Commit the updated reference files.

## New xlsx Drop Policy

1. Goldens protect the INA math model against the **reference corpus**
   (the xlsx files present at the 2026-05-28 baseline capture).
2. **New data files** (new months of DOS data, updated inventory/pipeline)
   are exercised via **integration tests** and **manual verification** —
   not via golden auto-regeneration.
3. **No auto-regeneration in CI** — golden references are committed
   artifacts, not generated during CI runs.
4. When new xlsx files change the numerical output, a developer must:
   - Run `--regenerate` locally
   - Review the diff in reference JSON files
   - Commit the updated references with a clear commit message
   - Include the reason for the change in the PR description
