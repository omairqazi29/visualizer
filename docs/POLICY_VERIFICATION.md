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
| DOS Monthly IV Issuances | travel.state.gov → Visa Statistics → Monthly IV Issuances | Monthly (~2-3 mo lag) | `data/DOS/*.xlsx` — consular visa issuances by country & category. Ground truth for FB usage, EB4/5 usage, restriction savings |
| USCIS EB I-485 Inventory | uscis.gov → Tools → Reports & Studies | Quarterly | `data/eb_inventory_*.xlsx` — pending I-485 cases by country, category, PD year. Drives demand/queue size |
| USCIS I-140 Performance | uscis.gov → Tools → Reports & Studies | Quarterly | `data/eb_i140_*performance*.xlsx` or `data/*performance*.xlsx` — approved I-140s awaiting visa numbers. Pipeline component of demand |
| Visa Bulletin | travel.state.gov → Visa Bulletin | Monthly | Sanity-check for India EB-1 FAD. Not directly ingested but used to validate projections |
| Presidential Proclamations | whitehouse.gov → Presidential Actions | As issued | Part of `ACTUAL_RESTRICTED_COUNTRIES` — 39 countries with entry suspension |
| DOS IV Pause (Public Charge) | travel.state.gov → Visa News → "IV Processing Updates..." | Indefinite (eff. Jan 21, 2026) | Part of `ACTUAL_RESTRICTED_COUNTRIES` — 75 countries with consular IV issuance paused |
| Report of the Visa Office | travel.state.gov → Annual Reports | Annual (~6 mo lag) | `DEFAULT_INDIA_EB1_SUPPLY` in `src/constants.py` — India's baseline EB-1 annual issuances |
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

### 5. Update Baseline Supply (Annual)

When a new Report of the Visa Office is published (e.g., FY2025):

1. Find India EB-1 issuances in Table V (Part II)
2. Update `DEFAULT_INDIA_EB1_SUPPLY` in `src/constants.py`
3. Update the comment with the source and value
4. Run tests

### 6. Cross-Verify Projections

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
| New USCIS inventory/pipeline | `data/*.xlsx` (drop-in) | `test_engine.py`, `test_parsers.py` |
| Baseline supply (new FY data) | `src/constants.py` | `test_constants.py`, `test_engine.py` |
| Court ruling on entry bans or IV pause | `src/constants.py` (countries), `api/main.py`, docs | `test_constants.py`, `test_engine.py` |
| Court ruling on USCIS holds only | docs only (no model impact) | — |

## Changelog

| Date | Event | Model Impact | Updated By |
|---|---|---|---|
| Jun 2026 | Added DOS 75-country IV pause to model. ACTUAL_RESTRICTED_COUNTRIES now union of 39-country Proclamation ban + 75-country IV pause = **91 countries**. Major additions: Brazil, Pakistan, Bangladesh, Egypt, Ethiopia, Colombia, Ghana, Iraq, Jamaica, Nepal, Russia, etc. | Significantly increased restriction savings — these are major IV consumers whose consular issuance is now paused | AI-assisted |
| Jun 5, 2026 | Dorcas v. USCIS — USCIS adjudicative hold vacated nationwide | None (DOS consular data unaffected; domestic I-485 processing is separate pathway) | AI-assisted |
| Jun 2026 | Expanded Proclamation countries from 18 to 39 (full scope of Proclamations 10949/10998) | Moderate increase in savings | AI-assisted |
| May 2026 | Initial researched values: India EB-1 = 6,952 (FY2024), 18-country restriction list | Baseline established | AI-assisted |