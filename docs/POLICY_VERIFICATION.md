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
| Presidential Proclamations | whitehouse.gov → Presidential Actions | As issued | Part of `ACTUAL_RESTRICTED_COUNTRIES` — 39 countries with entry suspension |
| DOS IV Pause (Public Charge) | travel.state.gov → Visa News → "IV Processing Updates..." | Indefinite (eff. Jan 21, 2026) | Part of `ACTUAL_RESTRICTED_COUNTRIES` — 75 countries with consular IV issuance paused |
| Report of the Visa Office | travel.state.gov → Annual Reports | Annual (~6 mo lag) | `DEFAULT_INDIA_EB1_SUPPLY` in `src/constants.py` + `INDIA_EB1_HISTORICAL` in `src/engine/supply.py` |
| Federal Court Rulings | CourtListener / PACER / news | As issued | May affect which policies are active (see below) |

## Step-by-Step Verification

### 1. Check Country Restriction List

The `ACTUAL_RESTRICTED_COUNTRIES` set in `src/constants.py` is the **union** of two overlapping policies. Both must be verified independently.

#### Policy 1: Presidential Proclamation Entry Ban (39 countries)
**Verify against:**
- Active Presidential Proclamations on whitehouse.gov (search "restricting entry foreign nationals")
- DOS travel advisories: travel.state.gov → News → Visas News
- USCIS Policy Memos: PM-602-0192, PM-602-0194 (or successors)

**What to check:** Any countries added/removed from entry suspensions? Proclamation revoked or superseded?

#### Policy 2: DOS 75-Country IV Pause (Public Charge)
**Verify against:**
- travel.state.gov → News → "Immigrant Visa Processing Updates for Nationalities at High Risk of U.S. Public Benefits Reliance"
- Check if the pause has been lifted, expanded, or if a court has enjoined it nationwide
- Pending lawsuit: CLINIC v. Rubio (1:26-cv-00858, S.D.N.Y.)

**What to check:** Any countries added/removed? Has a nationwide injunction been issued?

#### For both policies:
- India and China-mainland must remain EXCLUDED (they are beneficiaries, not targets)
- The union should include any country on EITHER list — if consular IVs are blocked for any reason, usage is zero
- Current union: **91 countries** (23 on both, 16 Proclamation-only, 52 IV-pause-only)

**How to update:**
Edit `ACTUAL_RESTRICTED_COUNTRIES` in `src/constants.py`. The set is organized with inline comments marking which source policy each country comes from. Also update `api/main.py` `get_methodology()` legal_status if policy status changes. No engine code changes needed.

### 2. Check Court Rulings

Court rulings can vacate, enjoin, or stay executive policies. They affect what the model should assume.

**Key distinction (critical for the model):**
- **Consular IV entry bans** (Presidential Proclamations) → affect DOS data (consular issuances). If vacated, restricted countries resume getting consular IVs → savings decrease.
- **USCIS adjudicative holds** (internal USCIS memos) → affect domestic I-485 processing only. NOT captured in DOS IV issuance data. If vacated, no change to DOS-derived savings.

**Current status (last verified: June 2026):**
- Entry bans (Proclamations 10949/10998): **In effect**. Consular IVs still suspended for 39 countries.
- DOS 75-country IV pause (public charge): **In effect**. Consular IV issuance paused for 75 countries. Lawsuit pending (*CLINIC v. Rubio*, S.D.N.Y.).
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

## Changelog

| Date | Event | Model Impact | Updated By |
|---|---|---|---|
| Jun 2026 | Data-driven supply model fix. (1) EB-4/5 spillover now uses TOTAL usage (consular+AOS) from `dhs_eb_category_usage.csv` parsed from DHS Yearbook XLSX — was using DOS consular-only. (2) India EB-1 share uses non-India demand subtraction from live I-485 inventory + DHS Yearbook — replaces backlog-ratio method. (3) SIV categories (SQ/SI/SD/SE/SK/SR/SU/SW) excluded from EB-4/5 restriction savings — Afghan/Iraqi SIVs are congressionally mandated, exempt from exec restrictions, confirmed by continued DOS issuance. Removes phantom 19.5k Afghan EB-4/5 "savings"; EB-4/5 spillover → 0 (oversubscribed even under restrictions). India EB-1: ~33k (was 44k with phantom spillover). Added Mar 2026 + Oct/Dec 2025 inventory snapshots. | Accurate supply: no phantom SIV savings, no hardcoded numbers | AI-assisted |
| Jun 2026 | Added Visa Bulletin Predictor. Extended VB history from Oct 2022 to Oct 2015 (387 rows, EB-1/EB-2/EB-3). New `VBPredictor` engine, `/api/vb-forecast` endpoint, `/vb-forecast` frontend page. 87+ EB-1 data points for advancement analysis. | New VB forecast capability — month-by-month FAD/DOF prediction with confidence bands | AI-assisted |
| Jun 2026 | Added DOS 75-country IV pause to model. ACTUAL_RESTRICTED_COUNTRIES now union of 39-country Proclamation ban + 75-country IV pause = **91 countries**. Major additions: Brazil, Pakistan, Bangladesh, Egypt, Ethiopia, Colombia, Ghana, Iraq, Jamaica, Nepal, Russia, etc. | Significantly increased restriction savings — these are major IV consumers whose consular issuance is now paused | AI-assisted |
| Jun 5, 2026 | Dorcas v. USCIS — USCIS adjudicative hold vacated nationwide | None (DOS consular data unaffected; domestic I-485 processing is separate pathway) | AI-assisted |
| Jun 2026 | Expanded Proclamation countries from 18 to 39 (full scope of Proclamations 10949/10998) | Moderate increase in savings | AI-assisted |
| May 2026 | Initial researched values: India EB-1 = 6,952 (FY2024), 18-country restriction list | Baseline established | AI-assisted |