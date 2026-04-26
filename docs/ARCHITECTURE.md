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
- Current reality: India EB-1 Final Action ~01APR23 (3yr backlog); FY26 forward movement observed.

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
2. SupplyCalculator.get_supply_breakdown(apply_freeze) -> Breakdown (with india_eb1_supply)
3. DemandModeler (supply, inventory+pipe total) -> projection + confidence
4. FastAPI endpoints (/waterfall, /supply-demand, /predict) -> Typed Next.js UI

See INA_MODEL.md (to be added) for equations. New data via src/scripts/update_data.py.

## Files of Interest
- api/main.py (endpoints + Pydantic)
- src/engine/supply.py (central math)
- frontend/src/app/{waterfall,supply-demand,predict}/page.tsx

(Previously documented Streamlit/Plotly version superseded by Next.js revamp.)
