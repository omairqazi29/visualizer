# Architecture: The Spillover Engine (Revamped 2026)

## Technology Stack (Current)
- **Backend**: FastAPI + Python 3.11 + Pandas (data cleaning for DOS/USCIS Excel)
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind + Recharts + shadcn/ui
- **Key Modeling**: INA 201/203 limits, vertical spillovers (EB4/5 -> EB-1), 7% caps + 202(a)(5) surplus, data-driven category-specific dependent multipliers from DHS Yearbook Table 7 (auto-updated from `data/DHS_Yearbook/dhs_table7_eb_multipliers.csv`; FY2015–FY2023; applied to I-140 pipeline only; I-485 inventory already includes dependents). EB-4/5 spillover uses TOTAL usage (consular + AOS) from `data/DHS_Yearbook/dhs_eb_category_usage.csv`, not DOS consular-only. India EB-1 share computed via non-India demand subtraction (live inventory + DHS Yearbook), not backlog ratio.
- **Data**: Monthly DOS IV issuances (any in data/DOS/ via directory load), USCIS EB I-485 Inventory + I-140 pipeline via src/data_discovery (auto latest eb_inventory*.xlsx and *performance*.xlsx / eb_i140*.xlsx by filename date or mtime), NVC backlog (ARIVA + monthly IV backlog reports in data/NVC/), DHS Yearbook EB category usage (`data/DHS_Yearbook/dhs_eb_category_usage.csv` — total/AOS/consular by FY, parsed from DHS Yearbook XLSX Table 7), DHS Yearbook Table 7 EB multipliers (`data/DHS_Yearbook/dhs_table7_eb_multipliers.csv`), Visa Bulletin history (data/visa_bulletin/ — India EB-1/EB-2/EB-3 FAD+DOF from Oct 2015, ~130 months), DOL PERM (data/DOL_PERM/), H-1B (data/H1B/), CEAC (data/CEAC/), I-485 flow (data/USCIS_I485/), processing times (data/USCIS_ProcessingTimes/). Drop-in support for new bulletins and quarterly releases.
- **Drop-in data caveats**: parsers auto-discover new files, but government releases vary in ways that need handling rather than trust. (1) The same reporting period is republished under different filenames (`i485_performance_fy2026_q1.xlsx` vs `i485_performance_data_fy2026_q1_v1.xlsx`), so glob-based loaders dedupe by period, not filename. (2) Cell storage changes between releases: the Feb 2026 inventory switched counts from text to numeric, so numeric parsing goes through `float()` before `int()`. (3) Filename conventions shift (DOL PERM used a two-digit `FY16` before FY2018), so fiscal-year regexes accept both widths. `tests/test_new_data_sources.py` pins all three.
- **Heavy-source caching**: the DOL PERM corpus (FY2015+, ~830MB of Excel) is normalized to a slim 11-column gzip cache under `data/DOL_PERM/.cache/`, keyed by source mtime+size and a `_CACHE_VERSION`. Cold build ~7 min, warm load ~1.6s. Bump `_CACHE_VERSION` in `perm_parser.py` whenever normalization logic changes.

## Research-Backed INA Fidelity Notes
- FB spillover (201(c)): Prior FY unused family (226k floor) added to EB pool. Scoped to the latest **complete** fiscal year (`DOSParser.get_complete_fys()` — 12 monthly files); DOS publishes monthly, so the in-progress FY is always partial and would manufacture phantom spillover against an annual limit.
- EB shares (203(b)): EB-1 28.6% + EB4/5 unused (roll-up); EB-2/3 fall-down.
- Per-country (202): 7% cap, surplus bypass for India/China backlogs.
- "Maximum Restriction Scenario" (`apply_freeze`): Hypothetical demand-curtailment on top-consuming countries NOT already restricted (Philippines, Mexico, Dominican Republic, Vietnam, China-mainland). Extends beyond the real 39-country restrictions. India excluded.
- **Real 2025-2026 policy (ONE policy in effect as of Aug 2026):**
  - *Proclamation entry ban (39 countries):* Proclamations 10949 (Jun 2025) + 10998 (eff. Jan 1, 2026) suspend IV entry. **In effect.** India/China explicitly excluded. This is the whole of `ACTUAL_RESTRICTED_COUNTRIES` today.
  - *DOS 75-country IV pause (eff. Jan 21, 2026):* **VACATED Aug 21, 2026** — CLINIC v. Rubio (S.D.N.Y., Judge Vargas) held it contrary to law and in excess of statutory authority; DOS's own page (updated Aug 28, 2026) states the pause "is no longer in effect." Removed from the current-policy set; kept as `DOS_IV_PAUSE_COUNTRIES_2026` for FY2026 historical attribution (in force Jan 21 – Aug 21, 2026, so FY2026 DOS data still reflects it).
  - *DOS IV interview pause (public-charge retraining, late Aug 2026):* Not modeled — a scheduling delay, not a numerical restriction.
  - *USCIS adjudicative hold (39 Proclamation countries):* Vacated Jun 5, 2026 (Dorcas v. USCIS). No model impact — affects domestic I-485 processing, not consular issuances measured by DOS.
  - Savings derived from actual DOS consular IV issuance data (ground truth). No dampening. Dropping the 52 IV-pause-only countries cuts modeled FY2025-based India EB-1 supply from **33,779 → 19,182**.
- Current reality (Sep 2026 VB): India EB-1 FAD holds **15OCT22**, DOF **01DEC23**; India EB-2 **U** (per-country limit reached, DOS notice May 22, 2026); India EB-3 FAD **01JAN14**. China EB-1 FAD **01JUL23**. DOS declared the FY2026 worldwide EB limit at **186,317** (FB 226,000; per-country 28,862, or 29,136 with EB-5 carryover) and warns India EB-1 may go Unavailable before FY end. Earlier (Jun 2026 VB): India EB-1 FAD retrogressed to 15DEC22 (from 01APR23 in May). DOS warned of possible "Unavailable" before FY end. FY2024 Visa Office: "~6,952 were issued to applicants chargeable to India" (out of 47,462 EB-1 total). USCIS Aug 2026 inv: 19,261 India EB-1 I-485 pending vs 6,539 China (peaked at 22,310 India in Mar 2026, now drawing down); data-driven India oversubscribed share = 0.747. No INA 201/203 amendments.

## Automated Data Ingestion

Public government data pages are scanned and (optionally) committed via a config-driven
pipeline — no hardcoded supply numbers; files drop into `data/` and are picked up by
`src/data_discovery.py` + existing parsers.

| Piece | Location |
|---|---|
| Source registry (DOS/USCIS/DHS/DOL + disabled stubs) | `src/ingestion/registry.py` |
| Scan / fetch / validate / security | `src/ingestion/scanner.py`, `fetcher.py`, `validator.py`, `security.py` |
| PR helper (`chore/data-*` + `gh pr create`) | `src/ingestion/pr_helper.py` |
| CLI | `python -m src.scripts.scan_and_pr` (`--scan` / `--fetch` / `--validate` / `--pr` / `--dry-run`) |
| Manual validate + automation pointer | `python -m src.scripts.update_data` |
| Scheduled workflows | `.github/workflows/data-scan.yml` (excludes `visa_bulletin`), `data-scan-visa-bulletin.yml` |
| Live smoke script | `scripts/verify_sources_live.py` |

Flow: public HTML pages → link match + host allowlist → download under `data/` → parser QA → optional PR.
Operational details, source groups (`all`, `all_including_vb`, `dos_iv`, `uscis`, …), and fail-closed
behavior are documented in `docs/POLICY_VERIFICATION.md` § Automated Data Ingestion.

## Core Components

### 1. Data Parsers (`src/parsers`)
- **BaseParser**: Header normalization (CHARGEABILITY_HEADERS), 'D'/<10 disclosure ->1 or mid.
- **DOSParser**: Auto header detection, FB_CATEGORIES sum, monthly_distribution for burn-rate.
- **InventoryParser** (revamped): Dynamic "Priority Date Year - XXXX" parsing for 2026+ reports; EB-1 filter handles full labels; no multiplier (I-485 already includes dependents per USCIS Q&A). Methods: `get_india_eb1_queue()`, `get_all_eb1_backlogs()`, `get_all_eb_backlogs()`.
- **PipelineParser**: I-140 approved awaiting visas. Data-driven category-specific dependent multipliers from DHS Yearbook Table 7 (via `get_data_driven_multipliers()`). Methods: `get_india_eb1_backlog()`, `get_all_eb_pipeline()`.
- **DhsYearbookParser**: DHS Yearbook Table 7 — computes principal-to-total multipliers by EB category from actual admissions data (FY2015–FY2023). Methods: `get_multipliers()`, `get_latest_multipliers()`, `get_historical_multipliers()`, `get_average_multipliers()`, `get_category_detail()`, `get_summary()`.
- **NVCParser**: NVC (National Visa Center) backlog — the hidden pipeline stage between I-140 approval and consular interview. Reads pre-extracted CSV data from DOS ARIVA PDFs (data/NVC/). Covers consular processing (CP) cases ONLY — disjoint from I-485 inventory (AOS). Includes derivatives (no multiplier). Methods: `get_eb_totals()`, `get_india_eb_nvc()`, `get_india_eb1_nvc()`, `get_eb_by_country()`, `get_iv_backlog()`, `get_yoy_comparison()`, `get_summary()`. Data: ARIVA Nov 2023 (260,660 EB worldwide; India 48,536 total, 2,426 EB-1). Monthly IV backlog report Sep 2024 (431k DQ cases, 385k pending scheduling).
- **VisaBulletinParser**: Historical India EB FAD/DOF data from `data/visa_bulletin/india_eb_history.csv` (Oct 2015–present, EB-1/EB-2/EB-3). Computes DOF-FAD gap statistics, current VB status for a given PD. Methods: `get_history()`, `get_all_categories_history()`, `compute_gaps()`, `get_dof_lead_months()`, `get_current_status()`.
- **I485FlowParser**: Monthly I-485 receipts vs. approvals from USCIS Congressional reports + quarterly performance data.
- **ProcessingTimesParser**: USCIS processing times by service center for EB I-485.
- **PERMParser**: DOL PERM Labor Certification data — leading indicator of EB-2/EB-3 I-140 filings.
- **H1BParser**: H-1B cap registration and approval data by country.
- **CEACParser**: Consular interview scheduling and issuance data from visawhen.com.
- **I140ReceiptsParser**: New I-140 petition filings by country and EB category.

### 2. Logic Engine (`src/engine`)
- **SupplyCalculator**: Waterfall = EB140k + FB_spill + EB45_spill + freeze_savings. Data-driven corrections: (1) EB-4/5 spillover uses total usage from DHS Yearbook CSV (not DOS consular-only — AOS unaffected by bans per Dorcas). (2) India EB-1 = total_eb1 − non_India_demand, where non-India demand is from live I-485 inventory (fallback: DHS Yearbook avg FY2023-2024). (3) SIV categories (SQ/SI/SD/SE/SK/SR/SU/SW — Afghan Allies Protection Act, Iraqi SIV) excluded from EB-4/5 restriction savings; they are congressionally mandated and exempt from executive restrictions (confirmed by continued DOS issuance post-Proclamation).
- **RedistributionEngine**: Freeze zeroing + distribute_spillover (7% cap then surplus bypass INA 202(a)(5)).
- **DemandModeler** (enhanced): Per-FY supply schedule from DOS data (varies by fiscal year); blends historical % with uniform for high-supply scenarios (threshold: >15,000 annual supply → 60% historical distribution + 40% uniform; see `src/engine/demand.py` lines 48-55); FY Oct reset with supply lookup.
- **VBPredictor**: Forecasts future Visa Bulletin FAD/DOF dates month-by-month. Decomposes historical VB movement into advancement rates and seasonal patterns (fiscal month). Blended forecast: 70% recent-12 avg + 30% seasonal, with supply-adjusted scaling and sqrt-widening confidence bands. Uses `VisaBulletinParser` for historical data and `VisaBulletinParser.get_dof_lead_months()` for DOF estimation. Methods: `get_advancement_rates()`, `get_seasonal_pattern()`, `get_advancement_stats()`, `forecast()`.
- **OppenheimSolver**: Predicts FAD via demand-supply equilibrium — models how DOS actually sets the cutoff date. Algorithm: (1) compute annual India EB-1 supply from INA cascade (via `SupplyCalculator`), (2) divide by 12 for monthly target, (3) binary search over the I-485 inventory demand curve (`InventoryParser.get_cumulative_demand()`) to find the FAD where `demand_below_FAD × materialization_rate ≈ monthly_target`. Auto-calibrates the materialization rate from the current VB FAD. Bridges VBPredictor (trend-based) and DemandModeler (burn-down) with actual demand-aware date-setting logic. Methods: `calibrate()`, `predict_next_fad()`, `predict_trajectory()`.

## Data Flow (Revamped)
1. DOS dir (all files) + Inventory/Pipeline via `InventoryParser.latest()` / `PipelineParser.latest()` (backed by `src/data_discovery.find_latest` + date/mtime sort) + NVC via `NVCParser("data/NVC")` -> Parsers (robust load + normalize)
2. SupplyCalculator.get_supply_breakdown(...) -> Breakdown
3. SupplyCalculator.get_supply_by_fy(...) -> {FY: India EB-1 supply}
4. DemandModeler (fy_supply=...) -> projection + confidence
5. VBPredictor.forecast() -> month-by-month FAD/DOF forecast with confidence bands
6. OppenheimSolver.calibrate() + predict_trajectory() -> demand-supply equilibrium FAD prediction
7. FastAPI endpoints (/waterfall, /supply-demand, /predict, /vb-forecast, /oppenheim, /nvc-backlog, /i485-flow, /processing-times, /perm-pipeline, /h1b-demand, /ceac-scheduling, /legislation, /i140-receipts, /inventory-context, /visa-bulletin-history, /dependent-multipliers, /methodology) using Parser.latest() + NVCParser -> Typed Next.js UI

See INA_MODEL.md (to be added) for equations. New data: drop files in data/ ; validated via `python -m src.scripts.update_data`.

## Files of Interest
- api/main.py (endpoints + Pydantic)
- src/engine/supply.py (central INA supply math)
- src/engine/vb_predictor.py (Visa Bulletin forecast engine — trend extrapolation)
- src/engine/oppenheim.py (Oppenheim FAD solver — demand-supply equilibrium)
- src/engine/demand.py (backlog clearance projection)
- src/engine/legislation.py (pending bills + what-if scenarios)
- frontend/src/app/{waterfall,supply-demand,predict,vb-forecast,legislation,...}/page.tsx

(Previously documented Streamlit/Plotly version superseded by Next.js revamp.)
