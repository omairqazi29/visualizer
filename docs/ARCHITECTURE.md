# Architecture: The Spillover Engine (Revamped 2026)

## Technology Stack (Current)
- **Backend**: FastAPI + Python 3.11 + Pandas (data cleaning for DOS/USCIS Excel)
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind + Recharts + shadcn/ui
- **Key Modeling**: INA 201/203 limits, vertical spillovers (EB4/5 -> EB-1), 7% caps + 202(a)(5) surplus, category-specific dependent multipliers (DHS Yearbook Table 7: EB-1 2.5x, EB-2 2.0x, EB-3 2.1x, EB-4/5 1.5x — applied to I-140 pipeline only; I-485 inventory already includes dependents)
- **Data**: Monthly DOS IV issuances (any in data/DOS/ via directory load), USCIS EB I-485 Inventory + I-140 pipeline via src/data_discovery (auto latest eb_inventory*.xlsx and *performance*.xlsx / eb_i140*.xlsx by filename date or mtime). Drop-in support for new bulletins and quarterly releases.

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
- Current reality (May 2026 VB): "India EB-1 Final Action Date (FAD): 01APR23" (https://travel.state.gov/.../visa-bulletin-for-may-2026.html). "High demand and number use by aliens chargeable to India in the EB-1 ... have made it necessary to retrogress the final action dates..." FY2024 Visa Office: "~6,952 were issued to applicants chargeable to India" (out of 47,462 EB-1 total). USCIS Feb 2026 inv: 22,335 India EB-1 I-485 pending (includes dependents, no multiplier needed). I-140 pipeline: 20,592 primary × 2.5 = 51,480. No INA 201/203 amendments.

## Core Components

### 1. Data Parsers (`src/parsers`)
- **BaseParser**: Header normalization (CHARGEABILITY_HEADERS), 'D'/<10 disclosure ->1 or mid.
- **DOSParser**: Auto header detection, FB_CATEGORIES sum, monthly_distribution for burn-rate.
- **InventoryParser** (revamped): Dynamic "Priority Date Year - XXXX" parsing for 2026+ reports; EB-1 filter handles full labels; no multiplier (I-485 already includes dependents per USCIS Q&A). Methods: `get_india_eb1_queue()`, `get_all_eb1_backlogs()`, `get_all_eb_backlogs()`.
- **PipelineParser**: I-140 approved awaiting visas. Category-specific dependent multipliers (EB-1: 2.5x, EB-2: 2.0x, EB-3: 2.1x, EB-4/5: 1.5x). Methods: `get_india_eb1_backlog()`, `get_all_eb_pipeline()`.

### 2. Logic Engine (`src/engine`)
- **SupplyCalculator**: Waterfall = EB140k + FB_spill + EB45_spill + freeze_savings. Computes india_eb1_supply.
- **RedistributionEngine**: Freeze zeroing + distribute_spillover (7% cap then surplus bypass INA 202(a)(5)).
- **DemandModeler** (enhanced): Per-FY supply schedule from DOS data (varies by fiscal year); blends historical % with uniform for high-supply scenarios; FY Oct reset with supply lookup.

## Data Flow (Revamped)
1. DOS dir (all files) + Inventory/Pipeline via `InventoryParser.latest()` / `PipelineParser.latest()` (backed by `src/data_discovery.find_latest` + date/mtime sort) -> Parsers (robust load + normalize)
2. SupplyCalculator.get_supply_breakdown(...) -> Breakdown
3. SupplyCalculator.get_supply_by_fy(...) -> {FY: India EB-1 supply}
4. DemandModeler (fy_supply=...) -> projection + confidence
4. FastAPI endpoints (/waterfall, /supply-demand, /predict) using Parser.latest() -> Typed Next.js UI

See INA_MODEL.md (to be added) for equations. New data: drop files in data/ ; validated via `python -m src.scripts.update_data`.

## Files of Interest
- api/main.py (endpoints + Pydantic)
- src/engine/supply.py (central math)
- frontend/src/app/{waterfall,supply-demand,predict}/page.tsx

(Previously documented Streamlit/Plotly version superseded by Next.js revamp.)
