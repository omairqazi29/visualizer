# Project Mandates: The Spillover Engine

## Source Control & Workflow
- **Conventional Commits**: All commits MUST follow the [Conventional Commits](https://www.conventionalcommits.org/) specification (e.g., `feat:`, `fix:`, `docs:`, `chore:`).
- **Branching Strategy**: Assume a PR-based workflow. New features or fixes should be developed on feature branches (e.g., `feat/feature-name`) before merging into the main branch.
- **Commit Granularity**: Keep commits surgical and focused on a single logical change.

## Architecture & Data
- **Python/Pandas**: Mandatory for data processing to handle messy government Excel/CSV headers and 'D' disclosure strings.
- **Dependent Multiplier**: Use data-driven category-specific multipliers from DHS Yearbook Table 7 (`get_data_driven_multipliers()`) for I-140 pipeline. I-485 inventory already includes dependents (no multiplier needed).
- **INA Logic**: Adhere to INA 201/203 spillover flow and the restriction redistribution logic as defined in the core engine.
- **VB Predictor**: The `VBPredictor` engine forecasts future Visa Bulletin dates using historical advancement rates + seasonal patterns. It's separate from `DemandModeler` (which does backlog burn-down). Both are in `src/engine/`.

## Data-Driven Supply Model (CRITICAL)
The supply model in `src/engine/supply.py` is the **single source of truth** for all visa supply numbers. It must stay data-driven — no hardcoded supply results anywhere.

### Rules
1. **No hardcoded supply numbers** in frontend pages, API endpoints, or docs. All supply data flows: `supply.py` → FastAPI endpoints (`api/main.py`) → `frontend/src/lib/api.ts` → page components.
2. **EB-4/5 spillover** uses TOTAL usage (consular + AOS) from `data/DHS_Yearbook/dhs_eb_category_usage.csv`. Never use DOS consular-only data for this — AOS is the majority of EB-4/5 and is unaffected by travel bans.
3. **India EB-1 share** uses demand subtraction: `total_eb1 − non_india_demand`. Non-India demand comes from live USCIS I-485 inventory (primary) or DHS Yearbook average (fallback). Never use a hardcoded percentage/ratio.
4. **Historical data** (e.g., `INDIA_EB1_HISTORICAL`) comes from Report of the Visa Office — acceptable as a dict since it's immutable published data. But anything derivable from data files in `data/` must be computed, not hardcoded.
5. **Fallback constants** (e.g., `40_510` for non-India demand) are last-resort values only, used when all data files are missing. They must be clearly commented as fallbacks.

### When Modifying `supply.py`
Any change to the supply model triggers mandatory updates to keep everything in sync:

| What to Update | File(s) | Why |
|---|---|---|
| Architecture docs | `docs/ARCHITECTURE.md` | Documents the supply calculation method |
| Verification docs | `docs/POLICY_VERIFICATION.md` | Documents data sources, update procedures, changelog |
| API response model | `api/main.py` (Pydantic model) | New fields must be exposed to frontend |
| API type definitions | `frontend/src/lib/api.ts` | TypeScript types must match Pydantic model |
| Waterfall page text | `frontend/src/app/waterfall/page.tsx` | Methodology descriptions must match actual logic |
| Methodology page | Verify `/methodology` still renders correctly | Auto-reflects backend, but check new sections |
| Tests | `tests/test_engine.py` | Must cover new/changed calculations |

### When Adding New Data Files
- Drop files in `data/` — parsers auto-discover them. No code changes needed.
- Run `python3 -m pytest tests/ -v` to validate.
- Update the changelog in `docs/POLICY_VERIFICATION.md`.

## Policy & Data Verification
When asked to update numbers, verify policies, or respond to legal/policy changes:

1. **Read `docs/POLICY_VERIFICATION.md` first** — it is the canonical process for all data and policy updates.
2. **DOS data is ground truth.** The model derives restriction savings from actual DOS consular IV issuance data (`data/DOS/*.xlsx`). Never apply artificial dampening factors to DOS-derived numbers.
3. **Distinguish consular vs domestic.** Presidential Proclamation entry bans affect consular IVs (DOS data, model uses this). USCIS adjudicative holds affect domestic I-485 processing (NOT in DOS data, no model impact). Court rulings must be evaluated against this distinction.
4. **Country list lives in `src/constants.py`** as `ACTUAL_RESTRICTED_COUNTRIES`. Must match current Presidential Proclamations + DOS IV pause. India and China-mainland must always be EXCLUDED.
5. **Data updates are drop-in.** New DOS/USCIS Excel files go in `data/` — auto-discovered by parsers. No code changes needed for new data files.
6. **Always run tests** after any change: `python3 -m pytest tests/ -v`
7. **Update the changelog** at the bottom of `docs/POLICY_VERIFICATION.md` after any policy or data change.
8. **The `/api/methodology` endpoint and frontend `/methodology` page** expose the current model parameters, country list, data sources, and legal status. Keep `api/main.py` `get_methodology()` in sync with `src/constants.py`.