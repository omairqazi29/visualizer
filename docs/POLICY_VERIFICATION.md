# Policy & Data Verification Process

How to cross-verify and update the numbers in The Spillover Engine.

## When to Verify

Check whenever any of these occur:
1. **New DOS monthly IV issuance data** released (travel.state.gov, typically 2-3 months lag)
2. **New USCIS quarterly data** released (I-485 inventory or I-140/I-360/I-526 performance data)
3. **New Visa Bulletin** posted (monthly, travel.state.gov — check India EB-1 FAD movement)
4. **Presidential Proclamation** issued or amended (whitehouse.gov — country list changes)
5. **Federal court ruling** affecting USCIS processing or entry bans (CourtListener, PACER, news)
6. **New fiscal year** Report of the Visa Office published (annual, ~6 month lag)

## Data Sources & What They Control

| Source | URL | Updates | Controls in Model |
|---|---|---|---|
| DOS Monthly IV Issuances | travel.state.gov → Visa Statistics → Monthly IV Issuances | Monthly (~2-3 mo lag) | `data/DOS/*.xlsx` — consular visa issuances by country & category. Ground truth for FB usage, restriction savings. Note: EB categories are consular-only (AOS not captured). |
| USCIS EB I-485 Inventory | uscis.gov → Tools → Reports & Studies | Monthly (~2-3 mo lag) | `data/eb_inventory_*.xlsx` — pending I-485 cases by country, category, PD year. Drives demand/queue size. Also provides live non-India EB-1 demand for supply model. |
| USCIS I-140 Performance | uscis.gov → Tools → Reports & Studies | Quarterly | `data/eb_i140_*performance*.xlsx` or `data/*performance*.xlsx` — approved I-140s awaiting visa numbers. Pipeline component of demand |
| DHS Yearbook / LIAR | ohss.dhs.gov → Immigration → Yearbook | Annual (~6-12 mo lag) | `data/DHS_Yearbook/dhs_eb_category_usage.csv` — total EB usage by category (consular + AOS) by FY. Critical for EB-4/5 spillover (DOS is consular-only). Also provides multipliers via `dhs_table7_eb_multipliers.csv`. |
| Visa Bulletin | travel.state.gov → Visa Bulletin | Monthly | `data/visa_bulletin/india_eb_history.csv` — historical FAD/DOF dates for India EB-1/EB-2/EB-3 (Oct 2015–present). Fed into `VBPredictor` for month-by-month forecast. **Must be updated monthly** with new bulletin dates. |
| Presidential Proclamations | whitehouse.gov → Presidential Actions | As issued | **All** of `ACTUAL_RESTRICTED_COUNTRIES` — 39 countries with entry suspension |
| DOS IV Pause (Public Charge) | travel.state.gov → Visa News → "IV Processing Updates..." | **Vacated Aug 21, 2026** (was eff. Jan 21, 2026) | Historical only — `DOS_IV_PAUSE_COUNTRIES_2026` (75 countries). No longer in `ACTUAL_RESTRICTED_COUNTRIES`. |
| Report of the Visa Office | travel.state.gov → Annual Reports | Annual (~6 mo lag) | `DEFAULT_INDIA_EB1_SUPPLY` in `src/constants.py` + `INDIA_EB1_HISTORICAL` in `src/engine/supply.py` |
| Federal Court Rulings | CourtListener / PACER / news | As issued | May affect which policies are active (see below) |

**Contextual/Indicator Data Sources** (not core supply model — these provide demand-side context and pipeline visibility):

| Source | Parser | API Endpoint | Role |
|---|---|---|---|
| DOL PERM Disclosure Data | `PERMParser` | `/api/perm-pipeline` | Leading indicator of EB-2/EB-3 I-140 filings (~12-24 month lead) |
| H-1B Cap Registration + Approvals | `H1BParser` | `/api/h1b-demand` | Future I-140 filing pressure — most India EB flows through H-1B first |
| CEAC Consular Scheduling | `CEACParser` | `/api/ceac-scheduling` | Real-time consular pipeline activity; validates DOS IV issuance projections |
| I-140 Receipts (New Filings) | `I140ReceiptsParser` | `/api/i140-receipts` | Queue growth rate — new I-140 petitions entering the system |
| USCIS Processing Times | `ProcessingTimesParser` | `/api/processing-times` | Domestic adjudication bottlenecks by service center for EB I-485 |
| USCIS I-485 Monthly Flow | `I485FlowParser` | `/api/i485-flow` | Inflow (receipts) vs. outflow (approvals) — is the I-485 queue growing or shrinking? |
| USCIS I-140 RADP | `I140RADPParser` | `/api/i140-radp` | Pending I-140 queue by EB subcategory (E11/E12/E13, E21/NIW, E31/E32/EW3) and beneficiary country of birth |
| USCIS Service-wide All Forms | `AllFormsParser` | `/api/all-forms` | Agency-wide volumes and published median processing times for every form on the EB path (I-140, I-485, I-765, I-131) |
| EB Inventory Trend | `InventoryParser.snapshots()` | `/api/inventory-series` | Observed queue direction across monthly snapshots; `burn_rate()` gives net change per month |
| DHS Tables 8-11 (New Arrivals / Adjustments) | `DHSNewAdjParser` | `/api/eb-path-split` | EB consular vs AOS split by FY and country (FY2018+); the only source reporting both paths on a common basis |

## Step-by-Step Verification

### 1. Check Country Restriction List

As of Aug 2026 the `ACTUAL_RESTRICTED_COUNTRIES` set in `src/constants.py` is the **Proclamation list only** (39 countries). It was the union of two overlapping policies until the DOS 75-country IV pause was vacated on Aug 21, 2026. Both policies are still documented below and must be verified independently.

#### Policy 1: Presidential Proclamation Entry Ban (39 countries)
**Verify against:**
- Active Presidential Proclamations on whitehouse.gov (search "restricting entry foreign nationals")
- DOS travel advisories: travel.state.gov → News → Visas News
- USCIS Policy Memos: PM-602-0192, PM-602-0194 (or successors)

**What to check:** Any countries added/removed from entry suspensions? Proclamation revoked or superseded?

#### Policy 2: DOS 75-Country IV Pause (Public Charge) — VACATED
**Status: no longer in effect.** On Aug 21, 2026 Judge Jeannette A. Vargas (S.D.N.Y.) held in *CLINIC et al. v. Rubio et al.* (1:26-cv-00858) that the categorical suspension was contrary to law and in excess of statutory authority under the INA/APA, vacated it, and set aside refusals based solely on it. DOS's own page (last updated Aug 28, 2026) now reads: "As of August 21, 2026, in accordance with the Court's order in CLINIC et al. v. Rubio, et al., the January 2026 pause of immigrant visa issuance to nationals of 75 countries is no longer in effect."

**Verify against:**
- travel.state.gov → News → "Immigrant Visa Processing Updates for Nationalities at High Risk of U.S. Public Benefits Reliance"
- Docket for CLINIC v. Rubio — watch for a government appeal (2d Cir.) or a stay pending appeal, which would put the 75 countries back in scope
- Any successor policy (e.g. a re-issued public-charge rule with notice-and-comment)

**What to check:** Has the vacatur been stayed or reversed? Has DOS re-issued the pause in another form? If so, restore `DOS_IV_PAUSE_COUNTRIES_2026` into `ACTUAL_RESTRICTED_COUNTRIES`.

**Related but NOT modeled:** in late Aug 2026 DOS paused immigrant visa *interview scheduling* worldwide for public-charge retraining. That shifts issuance timing, it does not zero a country's demand, so it is not a restriction input. Watch FY2026 Q4 / FY2027 Q1 DOS issuance for a timing dip.

#### For both policies:
- India and China-mainland must remain EXCLUDED (they are beneficiaries, not targets)
- The union should include any country on EITHER list — if consular IVs are blocked for any reason, usage is zero
- Current set: **39 countries** (Proclamation only). Historical union was 91 (23 on both lists, 16 Proclamation-only, 52 IV-pause-only); the 52 IV-pause-only countries left the set on Aug 21, 2026.

**How to update:**
Edit `ACTUAL_RESTRICTED_COUNTRIES` in `src/constants.py`. The set is organized with inline comments marking which source policy each country comes from. Also update `api/main.py` `get_methodology()` legal_status if policy status changes. No engine code changes needed.

### 2. Check Court Rulings

Court rulings can vacate, enjoin, or stay executive policies. They affect what the model should assume.

**Key distinction (critical for the model):**
- **Consular IV entry bans** (Presidential Proclamations) → affect DOS data (consular issuances). If vacated, restricted countries resume getting consular IVs → savings decrease.
- **USCIS adjudicative holds** (internal USCIS memos) → affect domestic I-485 processing only. NOT captured in DOS IV issuance data. If vacated, no change to DOS-derived savings.

**Current status (last verified: August 29, 2026):**
- Entry bans (Proclamations 10949/10998): **In effect**. Consular IVs still suspended for 39 countries. Cited by DOS in the Sep 2026 Visa Bulletin note C.
- DOS 75-country IV pause (public charge): **VACATED Aug 21, 2026** (*CLINIC v. Rubio*, S.D.N.Y., Judge Vargas). Confirmed by DOS on travel.state.gov (page updated Aug 28, 2026). No stay or appeal on the public record as of Aug 29, 2026. The 52 IV-pause-only countries were removed from `ACTUAL_RESTRICTED_COUNTRIES`; modeled FY2025-based India EB-1 supply falls **33,779 → 19,182**.
- DOS immigrant visa **interview** pause for public-charge retraining (late Aug 2026): **In effect**, no stated end date. Not modeled (timing, not a numerical restriction).
- USCIS adjudicative hold (PM-602-0192/0194): **Vacated** nationwide by Judge McConnell, June 5, 2026 (*Dorcas v. USCIS*, 1:26-cv-00132-JJM-PAS). I-485 processing resumes.
- **Model impact of adjudicative hold vacatur: None.** Savings are derived from DOS consular IV data (ground truth for consular issuances). The ruling affects USCIS domestic processing, a separate pathway not measured by DOS.

**If an entry ban OR the IV pause is vacated/stayed:**
That DOES affect the model — those countries would resume consular IV issuances → DOS data would show increased usage → savings from zeroing those countries would naturally decrease as new DOS data is loaded. Remove affected countries from `ACTUAL_RESTRICTED_COUNTRIES` in `src/constants.py` and update `api/main.py` `get_methodology()` legal_status.

### 3. Update DOS Data

When new monthly IV issuance Excel files are available:

```bash
# Download from travel.state.gov → Visa Statistics → Monthly Immigrant Visa Issuances
# File naming: "MONTH YEAR - IV Issuances by FSC or Place of Birth and Visa Class.xlsx"
# Drop into data/DOS/
cp "MONTH YEAR - IV Issuances by FSC or Place of Birth and Visa Class.xlsx" data/DOS/

# Validate
python3 -m pytest tests/ -v
```

No code changes needed — `DOSParser.load_from_directory()` auto-discovers all `.xlsx` files in `data/DOS/`.

### 4. Update USCIS Inventory / Pipeline Data

When new quarterly files are available:

```bash
# Inventory: download from uscis.gov, name like eb_inventory_MONTH_YEAR.xlsx
cp eb_inventory_april_2026.xlsx data/

# Pipeline/Performance: name like eb_i140_*performance*_fyYYYY_qN*.xlsx
cp eb_i140_i360_i526_performance_data_fy2026_q1_v1.xlsx data/

# Validate
python3 -m pytest tests/ -v
```

Auto-discovery (`src/data_discovery.py`) picks the latest file by parsed date or mtime.

### 5. Update Visa Bulletin History (Monthly)

When a new Visa Bulletin is posted on travel.state.gov:

1. Look up India EB-1, EB-2, and EB-3 Final Action Dates and Dates for Filing
2. Append 3 new rows (one per category) to `data/visa_bulletin/india_eb_history.csv`
3. Append the EB-1 row to `data/visa_bulletin/india_eb1_history.csv`
4. Format: `YYYY-MM,EB-X,India,YYYY-MM-DD,YYYY-MM-DD,travel.state.gov` (use "C" if Current)
5. Run tests: `python3 -m pytest tests/test_vb_predictor.py -v`

This feeds the VB Forecast (`/vb-forecast`) and improves the PD Predictor DOF estimates.

### 6. Update DHS Yearbook EB Data (Annual)

When a new DHS Yearbook (or LIAR quarterly report) is published:

1. Download the XLSX from ohss.dhs.gov → Immigration → Yearbook (Table 7)
2. Place in `data/DHS_Yearbook/`
3. Re-run the extraction script to regenerate `dhs_eb_category_usage.csv`:
   ```bash
   # The CSV stores total/AOS/consular by EB category and FY
   # Parsed from DHS Yearbook Table 7 and LIAR Table 1B
   python3 -c "from src.scripts.update_data import regenerate_dhs_csv; regenerate_dhs_csv()"
   # Or manually add rows to data/DHS_Yearbook/dhs_eb_category_usage.csv
   ```
4. This automatically updates: EB-4/5 total usage (spillover calc), non-India EB-1 demand (India share calc)
5. Run tests: `python3 -m pytest tests/ -v`

### 7. Update Baseline Supply (Annual)

When a new Report of the Visa Office is published (e.g., FY2025):

1. Find India EB-1 issuances in Table V (Part II)
2. Update `DEFAULT_INDIA_EB1_SUPPLY` in `src/constants.py`
3. Add the FY to `INDIA_EB1_HISTORICAL` in `src/engine/supply.py`
4. Add total worldwide EB-1 row to `data/DHS_Yearbook/dhs_eb_category_usage.csv`
5. Run tests

### 8. Cross-Verify Projections

After any data update, sanity-check against the current Visa Bulletin:

1. Run the API: `uvicorn api.main:app --reload`
2. Hit `/api/predict?priority_date=YYYY-MM-DD` with the current India EB-1 FAD from the latest Visa Bulletin
3. The confidence score and projected clearance date should be directionally consistent with observed FAD movement
4. Compare `/api/waterfall` output with statutory limits (EB base should be 140,000; FB floor 226,000)

## File Change Summary

| What Changed | Files to Update | Tests to Run |
|---|---|---|
| Country list (proclamation or IV pause change) | `src/constants.py`, `api/main.py` methodology | `test_constants.py`, `test_engine.py` |
| New DOS monthly data | `data/DOS/*.xlsx` (drop-in) | `test_engine.py`, `test_parsers.py` |
| New USCIS inventory/pipeline | `data/eb_inventory_*.xlsx` (drop-in) | `test_engine.py`, `test_parsers.py` |
| New DHS Yearbook | `data/DHS_Yearbook/*.xlsx` + regenerate `dhs_eb_category_usage.csv` | `test_engine.py` |
| Baseline supply (new FY data) | `src/constants.py`, `src/engine/supply.py`, `dhs_eb_category_usage.csv` | `test_constants.py`, `test_engine.py` |
| Court ruling on entry bans or IV pause | `src/constants.py` (countries), `api/main.py`, docs | `test_constants.py`, `test_engine.py` |
| Court ruling on USCIS holds only | docs only (no model impact) | — |
| New Visa Bulletin (monthly) | `data/visa_bulletin/india_eb_history.csv`, `india_eb1_history.csv` | `test_vb_predictor.py` |



## Automated Data Ingestion (GitHub Actions)

The repository includes an automated pipeline that scans public DOS / USCIS / DHS / DOL
pages for new Excel (and related) files, downloads them into the correct `data/` paths,
validates with existing parsers, and can open a PR. **No hardcoded supply numbers** — only
file placement; the engine still derives supply via `supply.py` + parsers.

### Components

| Piece | Location |
|---|---|
| Source registry | `src/ingestion/registry.py` |
| Scanner / fetcher / security | `src/ingestion/scanner.py`, `fetcher.py`, `security.py` |
| Validator (parser QA; not a security boundary) | `src/ingestion/validator.py` |
| PR helper | `src/ingestion/pr_helper.py` |
| CLI | `python -m src.scripts.scan_and_pr` |
| Manual validate + pointer | `python -m src.scripts.update_data` |
| Live smoke (integration) | `scripts/verify_sources_live.py` or `pytest -m integration` |
| Main scheduled workflow | `.github/workflows/data-scan.yml` — Mon/Thu 14:00 UTC + `workflow_dispatch` |
| Visa Bulletin cadence | `.github/workflows/data-scan-visa-bulletin.yml` — every 3 days + `workflow_dispatch` |

### Coverage matrix (enabled vs stub)

| Source id | Agency | Enabled | Notes |
|---|---|---|---|
| `dos_iv_fsc` | DOS | yes | FSC/Place of Birth xlsx only → `data/DOS/` |
| `visa_bulletin` | DOS | yes | Owned by VB workflow only; records `.seen_bulletins.txt` (not CSV history) |
| `uscis_inventory` | USCIS | yes | Often missing on landing page; `follow_links` depth-1; may need manual drop |
| `uscis_i485_perf` | USCIS | yes | → `data/USCIS_I485/` |
| `uscis_i140` | USCIS | yes | `eb_i140_*`, `i140_rec_*` → `data/` |
| `dhs_yearbook` | DHS | yes | `follow_links`; often no direct xlsx on OHSS page |
| `dol_perm` | DOL | yes | PERM disclosure xlsx/zip → `data/DOL_PERM/` |
| `nvc_waiting_list`, `uscis_i485_monthly_csv`, `uscis_processing_times`, `ceac_scheduling`, `h1b_data` | various | **no** (stubs) | Enable when URLs/patterns stabilize |

### Local usage

```bash
# List configured sources (incl. disabled stubs)
python -m src.scripts.scan_and_pr --list-sources

# Dry-run scan (network read-only; no downloads/commits)
python -m src.scripts.scan_and_pr --scan --dry-run

# Scan one agency group, download new files, validate parsers
python -m src.scripts.scan_and_pr --scan --fetch --validate --source dos_iv
python -m src.scripts.scan_and_pr --scan --fetch --validate --source uscis

# Open a PR (requires git + gh auth; not for normal local use unless intentional)
python -m src.scripts.scan_and_pr --scan --fetch --validate --pr --source all --dry-run

# Live page smoke (requires requests + network)
python scripts/verify_sources_live.py
```

Source groups: `all` (excludes `visa_bulletin`) | `all_including_vb` | `dos_iv` | `visa_bulletin` |
`uscis` | `uscis_inventory` | `uscis_i485_perf` | `uscis_i140` | `dhs` | `dol` | `supply`

### Behavior notes

- **Idempotent:** files already present under the target dir (by normalized/dedup name) are skipped.
  USCIS dedup normalizes `performancedata`↔`performance_data` and strips `_vN` only (does **not**
  collapse distinct form prefixes like `eb_i140` vs `i140_rec`).
- **Fail-closed:** scan failures, fetch failures, or validation failures exit non-zero and block `--pr`
  (use `--allow-scan-errors` only for exploratory scans).
- **Security:** per-source host allowlist; path traversal rejected; downloads capped at 80MB;
  `.xlsx`/`.xls` must start with zip/OLE magic; only paths under `data/` are staged for PRs.
- **DOS:** only `IV Issuances by FSC or Place of Birth` Excel files (not Post-level tables).
- **USCIS EB inventory:** landing page often has **no** `eb_inventory_*.xlsx`; scanner + `follow_links`
  watch for it; otherwise drop into `data/` manually (auto-discovery still applies).
- **Visa Bulletin:** main `all` group excludes VB (avoids duplicate PRs). Dedicated workflow records
  recent bulletin HTML URLs in `data/visa_bulletin/.seen_bulletins.txt`. Maintainers must still append
  FAD/DOF rows to `india_eb_history.csv` / `india_eb1_history.csv` (and China if applicable).
- **GHA:** single scan/fetch/validate/pr invocation per run; `source` is a choice allowlist passed via env;
  branch names include `GITHUB_RUN_ID`; default base branch is `master` (auto-detected).
- **Politeness:** User-Agent `SpilloverEngine-DataScanner/1.0 (+…/visualizer; …)`; ~1s delay; public pages only.
- **After a data PR merges:** run full tests; if supply/demand inputs changed, add a row to the
  **Changelog** below (AGENTS.md requirement).

### Docker e2e: mock-publish + scan pickup (no live government sites)

Offline/integration harness that proves the scanner picks up newly "published" files
without hitting travel.state.gov or uscis.gov.

| Piece | Location |
|---|---|
| Mock publisher (FastAPI) | `tests/e2e/mock_data_server/server.py` |
| Mock Dockerfile | `tests/e2e/mock_data_server/Dockerfile` |
| Compose profile `data-scan-e2e` | `docker-compose.data-scan-e2e.yml` |
| E2E tests (`@pytest.mark.e2e`) | `tests/e2e/test_data_scan_pickup.py` |
| Runner script | `scripts/e2e_data_scan_pickup.sh` |
| Docs | `tests/e2e/README.md` |

**Opt-in env overrides** (no production behavior change unless set): `INGESTION_DATA_DIR`,
`INGESTION_PROJECT_ROOT`, `INGESTION_SOURCE_URL_<source_id>`, `INGESTION_SOURCE_URL_OVERRIDES`
(JSON), `INGESTION_EXTRA_ALLOWED_HOSTS`, `INGESTION_REQUEST_DELAY_SEC`. See `src/ingestion/registry.py`.

> **Security:** Never set `INGESTION_*` in GitHub Actions (`data-scan*.yml`) or
> production/staging. Overrides redirect scans/downloads and extend host allowlists.
> Local/e2e mock runs only (this harness sets them explicitly).

```bash
# Start mock only (normal `docker compose up` unchanged — profile-gated)
docker compose -f docker-compose.yml -f docker-compose.data-scan-e2e.yml \
  --profile data-scan-e2e up --build -d mock-data-publisher

# Optional: parallel mock + API (api is in base docker-compose.yml, no profile)
docker compose -f docker-compose.yml -f docker-compose.data-scan-e2e.yml \
  --profile data-scan-e2e up --build -d mock-data-publisher api

# Run assertions (starts docker if needed, tears down mock on exit)
./scripts/e2e_data_scan_pickup.sh

# Or in-compose one-shot (publisher + scan-runner pytest container)
docker compose -f docker-compose.yml -f docker-compose.data-scan-e2e.yml \
  --profile data-scan-e2e run --rm scan-runner

# Local mock without Docker
python tests/e2e/mock_data_server/server.py
SKIP_DOCKER=1 ./scripts/e2e_data_scan_pickup.sh
```

Default unit suite excludes e2e/integration: `pytest` or `pytest -m 'not integration and not e2e'`.

### workflow_dispatch inputs (`data-scan.yml`)

- `source` — choice: `all` | `all_including_vb` | `dos_iv` | `uscis` | … (default `all`)
- `dry_run` — scan only, no commit/PR
- `skip_pr` — fetch + validate without opening a PR

## Changelog

| Date | Event | Model Impact | Updated By |
|---|---|---|---|
| Aug 29, 2026 | **DOF honesty pass + `VBPredictor` rate estimator repair.** **(A)** `/api/predict` now reports a DOF *range*, not just a point. The DOF date is derived (`clearance − median DOF-over-FAD lead`), and that lead is unstable: India EB-1 medians run **12.2 / 4.2 / 2.7 / 5.9** months over the last 12 / 24 / 36 / all bulletins, so the window choice alone moves the answer ~11 months. New fields `dof_estimate_earliest` / `_latest` / `_spread_months` / `_confidence` / `dof_gap_window_medians`, plus `dof_gap_inflated_by_retrogression` — the lead is currently wide because the **FAD retrogressed** (2023-04-01 → 2022-10-15 across Jun-Jul 2026) while the DOF sat frozen at 01DEC23 for 7 bulletins, and since the lead is *subtracted* from the clearance date, retrogression perversely makes the derived DOF look earlier. **(B)** `VBPredictor` was producing a 23-month FAD jump in a single bulletin: `seasonal_pattern` was a **mean over all 90 bulletins** (including the 2015-2018 year-long swings), giving terms of **+805 / −426 days** from ~7 samples, blended 30% and then multiplied by a 3.0x supply factor. Now: seasonality is a **median over a 36-bulletin window**, requires **5+ samples** per fiscal month (India EB-1 has exactly 3 → correctly yields **zero** seasonal adjustment), and is clamped to `3×base + 15` days; the base rate is a **winsorized p10-p90 mean over 24 bulletins** (**5.2 days/month**, 71% of months zero movement) rather than a raw mean that one +323-day bulletin sets; supply factor capped **3.0x → 2.0x**. DOF forecast rows now carry `dof_confidence_low/high` compounding the FAD band with the observed gap spread — previously the DOF shipped with **no uncertainty at all**. | Jan 2025 India EB-1 DOF: point **Feb 2027**, honest range **Jan 2027 – Dec 2027** (spread 11.2 mo, confidence `very_low`). The repaired trend extrapolation no longer reaches Jan 2025 within 36 months (was: Oct 2026) — the two methods now bracket rather than one being nonsense. FAD/clearance unchanged. | AI-assisted |
| Aug 29, 2026 | **`/api/predict` pipeline share: anchored to live data, plus opt-in overlap netting.** USCIS's "Approved Petitions Awaiting Visa Availability" report (`I140_I360_I526_app_wait_vis`, India EB-1 = **15,867** primaries as of Mar 2026) is country x preference category only — **no priority-date dimension** — so the share sitting ahead of a given PD must be modeled. **(1)** The old ramp was `min(1, ((year-2024)*12 + month) / 24)`, hardcoding the pipeline to Jan 2024 – Dec 2025; by Aug 2026 that was stale. It now anchors to the live Dates-for-Filing cutoff (`_current_dof_anchor()`, India EB-1 = **01DEC23**) and spreads to today, so the window grows with time (now **32 months**, was 24). A PD at or before the DOF gets **zero** pipeline ahead of it — the pipeline is by definition people who could not yet file. **(2)** New opt-in `net_pipeline_overlap` flag: the I-140 report is defined against the **FAD** chart (note 6) and excludes only people who already became LPR/USC (note 8), so people who filed an I-485 off the **DOF** chart and are still awaiting a number are counted by *both* reports. The Aug 2026 inventory puts that population at **13,455** persons of the 19,261 India EB-1 pending I-485s (`InventoryParser.get_india_eb1_by_visa_status()`). **Off by default** — the overlap follows from the report's definition but USCIS does not state it. Response now exposes `inventory_ahead` (observed) vs `pipeline_counted_ahead` (modeled) so the split is visible. | Jan 2025 India EB-1 PD, current policy: backlog_ahead **40,747 → 35,375** (fix 1) → **29,909** (fix 2); clearance **Oct 2028 → Jul 2028 → Mar 2028** | AI-assisted |
| Aug 29, 2026 | **I-485 monthly flow source enabled and backfilled through Jul 2026.** The `uscis_i485_monthly_csv` registry entry was a disabled stub because the filenames did not match the parser: USCIS publishes the series as `appropriation_requirement_<month>_<year>_v1.0.csv` while `I485FlowParser` keys off `monthly_<month>_<year>.csv`. Added `_normalize_uscis_monthly_report_name` and enabled the source, so new months are now picked up by the scan pipeline. USCIS links only the newest month on its data page (Jul 2026); May and Jun 2026 were backfilled through `fetch_candidate()` at the same documented path. Flow now runs to **Jul 2026**: EB I-485 pending **217,374 (Mar) → 244,568 (Apr) → 266,656 (May) → 270,157 (Jun) → 269,963 (Jul)** — a 45,289-receipt spike in Apr and 35,787 in May, against ~12-13k monthly approvals. The EB queue grew ~53k in four months and has only just flattened. Test: `test_uscis_monthly_report_name_maps_to_parser_filename`. | Demand side current through Jul 2026; no supply change | AI-assisted |
| Aug 29, 2026 | **The DOS 75-country immigrant visa pause was VACATED.** *CLINIC et al. v. Rubio et al.* (1:26-cv-00858, S.D.N.Y., Judge Jeannette A. Vargas), Aug 21, 2026: the categorical suspension is contrary to law and in excess of statutory authority under the INA/APA; the court vacated it and set aside refusals based solely on it. DOS's own page (updated Aug 28, 2026) states the pause "is no longer in effect." No stay or appeal on the public record. `ACTUAL_RESTRICTED_COUNTRIES` therefore drops from the 91-country union back to the **39 Proclamation countries** (10949/10998, still in effect); the 75-country list is retained as `DOS_IV_PAUSE_COUNTRIES_2026` for FY2026 historical attribution (in force Jan 21 – Aug 21, 2026). Separately, DOS paused immigrant visa *interview scheduling* worldwide for public-charge retraining — **not modeled** (timing, not a numerical restriction). | **Large decrease in modeled savings.** Current-policy India EB-1 supply (FY2025 DOS basis): **33,779 → 19,182** (−14,597). FB savings 62,269 → 16,839; FB spillover 108,851 → 63,421. Baseline (no restrictions) unchanged at 6,952. | AI-assisted |
| Aug 29, 2026 | **September 2026 Visa Bulletin** added (official travel.state.gov). India: EB-1 FAD holds **2022-10-15**, EB-2 still **U**, EB-3 holds **2014-01-01**; DOF unchanged (EB-1 **2023-12-01**, EB-2/3 **2015-01-15**). China EB-1 FAD holds **2023-07-01**. DOS published the FY2026 numerical limits: worldwide FB **226,000**, worldwide EB **186,317**, per-country **28,862** (**29,136** including EB-5 carryover), dependent-area 8,247 (8,325). DOS again warns India EB-1 may become Unavailable before FY end and that EB-2/EB-5 unreserved may retrogress. | VB forecast/Oppenheim anchor → Sep 2026; no date movement for India | AI-assisted |
| Aug 29, 2026 | **FY2026-Q2 USCIS data drop + four new inventory snapshots.** Fetched via `python -m src.scripts.scan_and_pr --scan --fetch`: EB I-485 inventory **May, Jun, Jul, Aug 2026**; `i485_performance_data_fy2026_q2`; `quarterly_all_forms_fy2026_q2`; `eb_i140_i360_i526_performancedata_fy2026_q2`; `i140_fy2026_q2` (RADP); `i140_rec_by_class_country_fy2026_q2`; plus DOL `PERM_Disclosure_Data_FY2026_Q3`. Aug 2026 inventory: India EB-1 pending **19,261** vs China **6,539** — India's EB-1 queue is drawing down from its Mar 2026 peak of 22,310, so the data-driven India oversubscribed share falls to **0.747** (was ~0.80). Test fixes: the RADP FY2026-Q2 workbook carries two quarters, so the all-forms cross-check now compares the *latest* quarter rather than the first. **DOS data:** travel.state.gov is behind a Cloudflare JS challenge, so the scanner still gets HTTP 403; **Jan 2026** and **Feb 2026** FSC files were pulled manually through Chrome. Oct/Nov/Dec 2025 are linked on the DOS page but those three FSC assets return 403 on every request — asset-specific, not rate limiting: from the same browser session Jan/Feb 2026 FSC returns 200, and so does the October 2025 *by Post* file, while October/November/December *by FSC* fail as both .xlsx and .pdf. Those three are broken on DOS's CDN; re-check periodically. So `data/DOS/` runs Oct 2022 – Sep 2025 plus Jan–Feb 2026. **Partial-FY guard added** (`DOSParser.get_fy_month_counts()` / `get_complete_fys()`): all annual-limit math in `supply.py` now scopes to the latest FY with 12 monthly files instead of `max(available_fys)`. Without it the 2-month FY2026 would have become the latest FY and produced **205,729** of FB spillover against the real FY2025 figure of **46,582** — a 4.4x inflation of the EB pool. Regression test: `test_partial_fiscal_year_is_excluded_from_annual_math`. | Demand side refreshed through Aug 2026; supply still on the FY2025 DOS basis | AI-assisted |
| Aug 2026 | **Critical parser fix: I-485 inventory counts were silently zeroed.** USCIS changed cell storage in the **February 2026** inventory release, so counts that were text (`"1802"`) became numeric and reach pandas as `"1802.0"`. `_parse_val` used `int(str(v))`, which raises on that string and returned **0**. Every affected cell was dropped from the totals. India EB-2 read as **453** instead of **25,544** (Apr 2026), India EB-3 as **241** instead of **15,795**, China EB-5 as **7,765** instead of **10,341**. Fixed by parsing via `float()`; regression test added (`tests/test_new_data_sources.py`). **Scope, measured by re-running both code paths over each snapshot:** only the Feb 2026, Mar 2026 and Apr 2026 releases are affected (Jan 2026 and earlier are byte-identical under both parsers), and within those only India EB-2/EB-3, China EB-5, and Feb-only India EB-5. **EB-1 is unaffected in every snapshot**, so the waterfall India EB-1 / non-India EB-1 headline figures do not change. | **Large but bounded**: India EB-2/EB-3 demand understated ~98% and China EB-5 ~25% from Feb 2026 on. EB-1 supply chain unchanged | AI-assisted |
| Aug 2026 | Ingested the FY2026-Q1 data drop. **New sources:** `DHSNewAdjParser` (DHS Tables 8-11) backfills the EB consular-vs-AOS split to **FY2018** (`dhs_eb_category_usage.csv` gains EB_TOTAL rows for FY2018-FY2021, regenerated by `python3 -m src.scripts.build_dhs_eb_usage`); `I140RADPParser` (`data/i140_fy*.xlsx`) exposes I-140 receipts/approvals/denials/**pending** by EB subcategory and country of birth; `AllFormsParser` reads the USCIS service-wide quarterly report. `InventoryParser.snapshots()`/`burn_rate()` turn the 10 monthly inventory releases into an observed queue trend. New endpoints: `/api/i140-radp`, `/api/all-forms`, `/api/inventory-series`, `/api/eb-path-split`. **Fixes:** FY2026-Q1 I-485 was double-counted (two filename variants both matched the glob; now deduped by period); PERM files named `FY15`/`FY16`/`FY17` parsed to fiscal year **0**, collapsing 313k rows into a phantom bucket; `/api/perm-pipeline` re-read 830MB of Excel per request (**422s → 1.6s** via a slim on-disk cache). | Demand-side detail and observed burn rate now data-driven | AI-assisted |
| Jul 2026 | **August 2026 Visa Bulletin** added (official travel.state.gov). India: EB-1 FAD holds **2022-10-15**, EB-2 still **U**, EB-3 holds **2014-01-01**; DOF unchanged (EB-1 **2023-12-01**, EB-2/3 **2015-01-15**). China EB-1 FAD advances to **2023-07-01**. DOS notes India EB-1 may go unavailable before FY end. | VB forecast/Oppenheim anchor → Aug 2026 | AI-assisted |
| Jul 2026 | Data refresh: July 2026 Visa Bulletin (India EB-1 FAD retrogressed to **2022-10-15**; EB-2 FAD **U**/Unavailable for remainder of FY2026; EB-3 FAD **2014-01-01**). Parser now accepts `U` (Unavailable). Added missing inventory snapshots (May/Aug/Sep 2025). I-485 monthly flow extended through **Apr 2026** (EB pending ~245k, still growing). Fetched USCIS I-485 perf FY2026 Q1, I-140 pipeline variants, historical PERM disclosures, DHS LPR/table archives. **Blocked:** travel.state.gov DOS IV HTML (HTTP 403) — no FY2026 DOS monthly FSC files beyond Sep 2025; inventory still latest **Apr 2026**. Supply still FY2025 DOS-based (~33.6k India EB-1 w/ restrictions). | VB current FAD/DOF + EB-2 unavailable | AI-assisted |
| Jun 2026 | Added Docker data-scan e2e harness (mock-data-publisher + `INGESTION_*` env overrides + compose profile `data-scan-e2e`). Proves scan/fetch/publish-delta pickup without live government sites. | No model number change | AI-assisted |
| Jun 2026 | Data-scan review fixes: single GHA invocation, host/path security, fail-closed PR gate, `master`/auto base branch, VB excluded from main `all` group, disabled stubs, live verify script, ARCHITECTURE/AGENTS/POLICY docs. | No model number change | AI-assisted |
| Jun 2026 | Added automated data-scan pipeline (`src/ingestion/`, `scan_and_pr` CLI, GitHub Actions `data-scan.yml` + `data-scan-visa-bulletin.yml`). Scans DOS IV FSC, USCIS I-140/I-485 perf/inventory patterns, DHS/DOL pages; opens chore/data-* PRs when new files appear. | No model number change by itself — enables faster drop-in data updates | AI-assisted |
| Jun 2026 | Data-driven supply model fix. (1) EB-4/5 spillover now uses TOTAL usage (consular+AOS) from `dhs_eb_category_usage.csv` parsed from DHS Yearbook XLSX — was using DOS consular-only. (2) India EB-1 share uses non-India demand subtraction from live I-485 inventory + DHS Yearbook — replaces backlog-ratio method. (3) SIV categories (SQ/SI/SD/SE/SK/SR/SU/SW) excluded from EB-4/5 restriction savings — Afghan/Iraqi SIVs are congressionally mandated, exempt from exec restrictions, confirmed by continued DOS issuance. Removes phantom 19.5k Afghan EB-4/5 "savings"; EB-4/5 spillover → 0 (oversubscribed even under restrictions). India EB-1: ~33k (was 44k with phantom spillover). Added Mar 2026 + Oct/Dec 2025 inventory snapshots. | Accurate supply: no phantom SIV savings, no hardcoded numbers | AI-assisted |
| Jun 2026 | Added Visa Bulletin Predictor. Extended VB history from Oct 2022 to Oct 2015 (387 rows, EB-1/EB-2/EB-3). New `VBPredictor` engine, `/api/vb-forecast` endpoint, `/vb-forecast` frontend page. 87+ EB-1 data points for advancement analysis. | New VB forecast capability — month-by-month FAD/DOF prediction with confidence bands | AI-assisted |
| Jun 2026 | Added DOS 75-country IV pause to model. ACTUAL_RESTRICTED_COUNTRIES now union of 39-country Proclamation ban + 75-country IV pause = **91 countries**. Major additions: Brazil, Pakistan, Bangladesh, Egypt, Ethiopia, Colombia, Ghana, Iraq, Jamaica, Nepal, Russia, etc. | Significantly increased restriction savings — these are major IV consumers whose consular issuance is now paused | AI-assisted |
| Jun 5, 2026 | Dorcas v. USCIS — USCIS adjudicative hold vacated nationwide | None (DOS consular data unaffected; domestic I-485 processing is separate pathway) | AI-assisted |
| Jun 2026 | Expanded Proclamation countries from 18 to 39 (full scope of Proclamations 10949/10998) | Moderate increase in savings | AI-assisted |
| May 2026 | Initial researched values: India EB-1 = 6,952 (FY2024), 18-country restriction list | Baseline established | AI-assisted |