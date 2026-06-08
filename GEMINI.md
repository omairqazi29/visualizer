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

## Policy & Data Verification (IMPORTANT)
When asked to update numbers, verify policies, or respond to legal/policy changes:

1. **Read `docs/POLICY_VERIFICATION.md` first** — it is the canonical process for all data and policy updates.
2. **DOS data is ground truth.** The model derives restriction savings from actual DOS consular IV issuance data (`data/DOS/*.xlsx`). Never apply artificial dampening factors to DOS-derived numbers.
3. **Distinguish consular vs domestic.** Presidential Proclamation entry bans affect consular IVs (DOS data, model uses this). USCIS adjudicative holds affect domestic I-485 processing (NOT in DOS data, no model impact). Court rulings must be evaluated against this distinction.
4. **Country list lives in `src/constants.py`** as `ACTUAL_RESTRICTED_COUNTRIES`. Must match current Presidential Proclamations. India and China-mainland must always be EXCLUDED.
5. **Data updates are drop-in.** New DOS/USCIS Excel files go in `data/` — auto-discovered by parsers. No code changes needed for new data files.
6. **Always run tests** after any change: `python3 -m pytest tests/ -v`
7. **Update the changelog** at the bottom of `docs/POLICY_VERIFICATION.md` after any policy or data change.
8. **The `/api/methodology` endpoint and frontend `/methodology` page** expose the current model parameters, country list, data sources, and legal status. Keep `api/main.py` `get_methodology()` in sync with `src/constants.py`.
