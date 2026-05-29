# Architecture: The Spillover Engine (Revamped 2026)

## Technology Stack
- **Backend**: FastAPI + Python 3.11 + Pandas (data cleaning for DOS/USCIS Excel)
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind + Recharts + shadcn/ui
- **Key Modeling**: INA 201/203 limits, vertical spillovers (EB4/5 -> EB-1), 7% caps + 202(a)(5) surplus, 2.2x dependents (per project mandate)
- **Data**: Monthly DOS IV issuances (any in data/DOS/ via directory load), USCIS EB I-485 Inventory + I-140 pipeline via src/data_discovery (auto latest eb_inventory*.xlsx and *performance*.xlsx / eb_i140*.xlsx by filename date or mtime). Drop-in support for new bulletins and quarterly releases.

## Layer Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                    │
│  page.tsx → shared hooks (useWaterfallData, etc.)       │
│  → @/lib/api.ts → FastAPI                               │
├─────────────────────────────────────────────────────────┤
│                  API Layer (FastAPI)                     │
│  api/main.py  — thin routes, Pydantic models            │
├─────────────────────────────────────────────────────────┤
│         Application Services (PR6)  [*]                 │
│  src/application/ — SupplyService,                      │
│  DemandProjectionService, DataSourceService             │
├─────────────────────────────────────────────────────────┤
│                 Domain Layer (Pure)                      │
│  src/domain/ — value_objects, policies (Strategy),      │
│  protocols (DIP), exceptions — no pandas, no I/O        │
├─────────────────────────────────────────────────────────┤
│               Engine (Computation)                      │
│  src/engine/ — SupplyCalculator (DI-based),             │
│  RedistributionEngine, DemandModeler                    │
├─────────────────────────────────────────────────────────┤
│                    Adapters                              │
│  src/adapters/ — PandasDOSLoader (DOSDataLoader impl)   │
├─────────────────────────────────────────────────────────┤
│                 Data Parsers                             │
│  src/parsers/ — DOSParser, InventoryParser,             │
│  PipelineParser, BaseParser                             │
└─────────────────────────────────────────────────────────┘
```

Dependencies flow downward only. Domain has zero external dependencies.

> **[*] Note:** The Application Services layer (`src/application/`) is introduced in PR6 of the refactoring stack and may not be present on all branches. Until the full stack is merged, `api/main.py` calls `src/engine/` and `src/parsers/` directly. This diagram describes the target architecture after all 8 PRs are assembled.

## Research-Backed INA Fidelity Notes
- FB spillover (201(c)): Prior FY unused family (226k floor) added to EB pool.
- EB shares (203(b)): EB-1 28.6% + EB4/5 unused (roll-up); EB-2/3 fall-down.
- Per-country (202): 7% cap, surplus bypass for India/China backlogs.
- "75-Country Freeze": Hypothetical demand-curtailment scenario (not enacted policy as of May 2026 bulletins). India excluded from default restricted list.
- **Real 2025-2026 policy (distinct):** Presidential Proclamations 10949 (Jun 2025) + 10998 (Dec 2025, eff Jan 2026) suspend IVs for specific countries (full: Afghanistan, Haiti, Iran, etc.; partial incl. Nigeria, Venezuela, Cuba; **India/China explicitly excluded** per DOS). "allowed some reallocation of visa numbers to other countries under INA limits." (travel.state.gov). ACTUAL_RESTRICTED_COUNTRIES models this for accurate spillover.
- Current reality (May 2026 VB): "India EB-1 Final Action Date (FAD): 01APR23" (https://travel.state.gov/.../visa-bulletin-for-may-2026.html). "High demand and number use by aliens chargeable to India in the EB-1 ... have made it necessary to retrogress the final action dates..." FY2024 Visa Office: "~6,952 were issued to applicants chargeable to India" (out of 47,462 EB-1 total). USCIS Jan 2026 inv: 48,162 (2.2x) India EB-1 pending. No INA 201/203 amendments.

## Core Components

### 1. Domain Layer (`src/domain/`)
- **value_objects.py**: `PolicyName` enum, immutable value types — no I/O, no pandas.
- **policies.py**: `StandardPolicy`, `FreezePolicy`, `RealRestrictionsPolicy` — Strategy pattern implementing `SpilloverPolicy` protocol. Each encapsulates scenario-specific savings computation.
- **protocols.py**: `SpilloverPolicy`, `DOSDataLoader` — `@runtime_checkable` Protocol classes for DIP boundaries.
- **exceptions.py**: Domain-specific exception hierarchy.

### 2. Adapters (`src/adapters/`)
- **PandasDOSLoader**: Implements `DOSDataLoader` protocol; wraps `DOSParser` for file I/O.

### 3. Application Services (`src/application/`) — *introduced in PR6*
- **SupplyService**: Orchestrates `SupplyCalculator` with policy resolution.
- **DemandProjectionService**: Orchestrates demand modeling and trajectory projection.
- **DataSourceService**: Data file discovery and metadata.

> Until the full PR stack is merged, `api/main.py` calls engine/parsers directly. See PR6 for the service layer wiring.

### 4. Data Parsers (`src/parsers/`)
- **BaseParser**: Header normalization (CHARGEABILITY_HEADERS), 'D'/<10 disclosure ->1 or mid.
- **DOSParser**: Auto header detection, FB_CATEGORIES sum, monthly_distribution for burn-rate.
- **InventoryParser** (revamped): Dynamic "Priority Date Year - XXXX" parsing for 2026+ reports; EB-1 filter handles full labels; total *2.2x.
- **PipelineParser**: I-140 approved awaiting visas (India EB-1 row).

### 5. Engine (`src/engine/`)
- **SupplyCalculator**: DI-based waterfall computation (EB140k + FB_spill + EB45_spill + policy savings). Accepts loader and policy via constructor. Computes india_eb1_supply.
- **RedistributionEngine**: Freeze zeroing + distribute_spillover (7% cap then surplus bypass INA 202(a)(5)).
- **DemandModeler** (enhanced): Blends historical % with uniform for high-supply (freeze) scenarios; FY Oct reset.

### 6. Frontend (`frontend/src/`)
- **Shared hooks** (`lib/hooks/`): `useWaterfallData`, `useSupplyDemandData`, `usePredictData` — encapsulate API calls, loading/error state, and mode switching. All page components consume these hooks.
- **Pages** (`app/`): `page.tsx` (dashboard), `waterfall/page.tsx`, `supply-demand/page.tsx`, `predict/page.tsx` — pure rendering; data fetching delegated to hooks.

## Data Flow
1. DOS dir (all files) + Inventory/Pipeline via `InventoryParser.latest()` / `PipelineParser.latest()` (backed by `src/data_discovery.find_latest` + date/mtime sort) → Parsers (robust load + normalize)
2. `PandasDOSLoader.load_all_issuances()` → `SupplyCalculator` (injected via DIP)
3. Policy strategy (`StandardPolicy` / `FreezePolicy` / `RealRestrictionsPolicy`) → `SupplyCalculator._compute_with_policy()` → `SupplyBreakdown`
4. `DemandModeler` → projection + confidence
5. FastAPI endpoints (`/waterfall`, `/supply-demand`, `/predict`) → typed JSON
6. Frontend hooks → React pages → Recharts visualization

New data: drop files in `data/`; validated via `python -m src.scripts.update_data`.

## Files of Interest
- `api/main.py` — endpoints + Pydantic response models
- `src/engine/supply.py` — central waterfall math (DI, Strategy)
- `src/domain/policies.py` — spillover policy strategies
- `src/domain/protocols.py` — DIP boundary protocols
- `frontend/src/lib/hooks/` — shared data hooks
- `frontend/src/app/{waterfall,supply-demand,predict}/page.tsx`
- `tests/golden/` — reference output regression harness

## Test Strategy
- **Golden regression** (`tests/golden/capture_and_verify.py`): Reference JSON outputs (6952 / 78837 / 31053 / 93464) verified on every CI run.
- **Property-based tests** (Hypothesis): Invariants on policy strategies and supply computation.
- **Unit tests**: Domain layer (pure, fast), adapter integration, hook smoke tests (MSW + vitest).
- **Coverage target**: 80%+ on `src/` package.

---

## Refactoring Summary (2026, Complete)

An 8-PR refactoring effort introduced a Clean-inspired layered architecture.

| PR | Scope |
|----|-------|
| PR1 | Domain layer: value objects, policies, exceptions, protocols |
| PR2 | Parser refactoring behind interfaces + isolated unit tests |
| PR3 | SpilloverPolicy Strategy family (Standard/Freeze/RealRestrictions) |
| PR4 | SupplyCalculator DI refactoring + PandasDOSLoader adapter |
| PR5 | Frontend shared data hooks + MSW smoke tests + vitest config |
| PR6 | Application Services (SupplyService, DemandProjectionService, DataSourceService) |
| PR7 | Test strategy: goldens, Hypothesis properties, coverage config |
| PR8 | Full cutover: frontend pages consume hooks, shadow removal, cleanup |

Key decisions:
- **Strategy pattern** for spillover policies — open/closed for new scenarios.
- **Dependency Inversion** at the engine boundary via `DOSDataLoader` protocol.
- **Shadow dual-run** during transition (PR4-PR7) verified fidelity before legacy removal in PR8.
- **Zero behavior change** throughout — same API responses, same UI rendering.
- Existing `src/parsers/`, `src/engine/`, `src/constants.py` remain in place; only internal wiring changed.
