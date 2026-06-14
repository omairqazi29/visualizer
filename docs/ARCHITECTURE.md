# Architecture: The Spillover Engine (Revamped 2026)

## Technology Stack (Current)
- **Backend**: FastAPI + Python 3.11 + Pandas (data cleaning for DOS/USCIS Excel)
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind + Recharts + shadcn/ui
- **Key Modeling**: INA 201/203 limits, vertical spillovers (EB4/5 -> EB-1), 7% caps + 202(a)(5) surplus, data-driven category-specific dependent multipliers from DHS Yearbook Table 7 (auto-updated from `data/DHS_Yearbook/dhs_table7_eb_multipliers.csv`; FY2015–FY2023; applied to I-140 pipeline only; I-485 inventory already includes dependents). EB-4/5 spillover uses TOTAL usage (consular + AOS) from `data/DHS_Yearbook/dhs_eb_category_usage.csv`, not DOS consular-only. India EB-1 share computed via non-India demand subtraction (live inventory + DHS Yearbook), not backlog ratio.
- **Data**: Monthly DOS IV issuances (any in data/DOS/ via directory load), USCIS EB I-485 Inventory + I-140 pipeline via src/data_discovery (auto latest eb_inventory*.xlsx and *performance*.xlsx / eb_i140*.xlsx by filename date or mtime), NVC backlog (ARIVA + monthly IV backlog reports in data/NVC/), DHS Yearbook EB category usage (`data/DHS_Yearbook/dhs_eb_category_usage.csv` — total/AOS/consular by FY, parsed from DHS Yearbook XLSX Table 7), DHS Yearbook Table 7 EB multipliers (`data/DHS_Yearbook/dhs_table7_eb_multipliers.csv`), Visa Bulletin history (data/visa_bulletin/ — India EB-1/EB-2/EB-3 FAD+DOF from Oct 2015, ~130 months), DOL PERM (data/DOL_PERM/), H-1B (data/H1B/), CEAC (data/CEAC/), I-485 flow (data/USCIS_I485/), processing times (data/USCIS_ProcessingTimes/). Drop-in support for new bulletins and quarterly releases.

## Research-Backed INA Fidelity Notes
- FB spillover (201(c)): Prior FY unused family (226k floor) added to EB pool.
- EB shares (203(b)): EB-1 28.6% + EB4/5 unused (roll-up); EB-2/3 fall-down.
- Per-country (202): 7% cap, surplus bypass for India/China backlogs.
- "Maximum Restriction Scenario" (`apply_freeze`): Hypothetical demand-curtailment on top-consuming countries NOT already restricted (Philippines, Mexico, Dominican Republic, Vietnam, China-mainland). Extends beyond the real 91-country restrictions. India excluded.
- **Real 2025-2026 policy (TWO stacking policies):**
  - *Proclamation entry ban (39 countries):* Proclamations 10949 (Jun 2025) + 10998 (Dec 2025) suspend IV entry. India/China explicitly excluded.
  - *DOS 75-country IV pause (eff. Jan 21, 2026):* Consular IV issuance paused for 75 countries (public charge risk). Adds major countries not on Proclamation: Brazil, Pakistan, Bangladesh, Egypt, Ethiopia, Colombia, Ghana, Iraq, etc. Pending lawsuit: CLINIC v. Rubio (S.D.N.Y.).
  - *Union = 91 countries* in `ACTUAL_RESTRICTED_COUNTRIES`. Savings derived from actual DOS consular IV issuance data (ground truth). No dampening.
  - *USCIS adjudicative hold (39 Proclamation countries):* Vacated Jun 5, 2026 (Dorcas v. USCIS). No model impact — affects domestic I-485 processing, not consular issuances measured by DOS.
- Current reality (Jun 2026 VB): India EB-1 FAD retrogressed to 15DEC22 (from 01APR23 in May). DOS warned of possible "Unavailable" before FY end. FY2024 Visa Office: "~6,952 were issued to applicants chargeable to India" (out of 47,462 EB-1 total). USCIS Mar 2026 inv: 22,310 India EB-1 I-485 pending (grew from 15,412 in Oct 2025 — filing surge outpacing approvals). I-140 pipeline: 20,592 primary × 2.5 = 51,480. No INA 201/203 amendments.

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
