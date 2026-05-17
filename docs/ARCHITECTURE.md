# Architecture: The Spillover Engine (Revamped 2026)

## Technology Stack (Current)
- **Backend**: FastAPI + Python 3.11 + Pandas (data cleaning for DOS/USCIS Excel)
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind + Recharts + shadcn/ui
- **Key Modeling**: INA 201/203 limits, vertical spillovers (EB4/5 -> EB-1), 7% caps + 202(a)(5) surplus, 2.2x dependents (per project mandate)
- **Data**: Monthly DOS IV issuances (FY25), USCIS EB I-485 Inventory (Jan 2026), I-140 pipeline (FY25 Q4)

## Research-Backed INA Fidelity Notes
- FB spillover (201(c)): Prior FY unused family (226k floor) added to EB pool.
- EB shares (203(b)): EB-1 28.6% + EB4/5 unused (roll-up); EB-2/3 fall-down.
- Per-country (202): 7% cap, surplus bypass for India/China backlogs.
- "75-Country Freeze": Hypothetical demand-curtailment scenario (not enacted policy as of May 2026 bulletins). India excluded from default restricted list.
- **Real 2025-2026 policy (distinct):** Presidential Proclamations 10949 (Jun 2025) + 10998 (Dec 2025, eff Jan 2026) suspend IVs for specific countries (full: Afghanistan, Haiti, Iran, etc.; partial incl. Nigeria, Venezuela, Cuba; **India/China explicitly excluded** per DOS). "allowed some reallocation of visa numbers to other countries under INA limits." (travel.state.gov). ACTUAL_RESTRICTED_COUNTRIES models this for accurate spillover.
- Current reality (May 2026 VB): "India EB-1 Final Action Date (FAD): 01APR23" (https://travel.state.gov/.../visa-bulletin-for-may-2026.html). "High demand and number use by aliens chargeable to India in the EB-1 ... have made it necessary to retrogress the final action dates..." FY2024 Visa Office: "~6,952 were issued to applicants chargeable to India" (out of 47,462 EB-1 total). USCIS Jan 2026 inv: 48,162 (2.2x) India EB-1 pending. No INA 201/203 amendments.

## Core Components

### 1. Data Parsers (`src/parsers`)
- **BaseParser**: Header normalization (CHARGEABILITY_HEADERS), 'D'/<10 disclosure ->1 or mid.
- **DOSParser**: Auto header detection, FB_CATEGORIES sum, monthly_distribution for burn-rate.
- **InventoryParser** (revamped): Dynamic "Priority Date Year - XXXX" parsing for 2026+ reports; EB-1 filter handles full labels; total *2.2x.
- **PipelineParser**: I-140 approved awaiting visas (India EB-1 row).

### 2. Logic Engine (`src/engine`)
- **SupplyCalculator**: Waterfall = EB140k + FB_spill + EB45_spill + freeze_savings. Computes india_eb1_supply.
- **RedistributionEngine**: Freeze zeroing + distribute_spillover (7% cap then surplus bypass INA 202(a)(5)).
- **DemandModeler** (enhanced): Blends historical % with uniform for high-supply (freeze) scenarios; FY Oct reset.

## Data Flow (Revamped)
1. DOS dir + Inventory xlsx -> Parsers (robust load + normalize)
2. SupplyCalculator.get_supply_breakdown(apply_freeze, apply_real_restrictions=False) -> Breakdown (with india_eb1_supply; real_restrictions adds actual policy spillover)
3. DemandModeler (supply, inventory+pipe total) -> projection + confidence
4. FastAPI endpoints (/waterfall, /supply-demand, /predict) -> Typed Next.js UI

See INA_MODEL.md (to be added) for equations. New data via src/scripts/update_data.py.

## Files of Interest
- api/main.py (endpoints + Pydantic)
- src/engine/supply.py (central math)
- frontend/src/app/{waterfall,supply-demand,predict}/page.tsx

(Previously documented Streamlit/Plotly version superseded by Next.js revamp.)
