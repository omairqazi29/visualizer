# The Spillover Engine 🇺🇸 📈

A modern web application to visualize and predict the impact of U.S. Immigrant Visa restrictions on the India EB-1 backlog (INA 201/203 spillover modeling, revamped 2026 with current Visa Bulletin and restriction policy data).

## Stack
- **Backend**: FastAPI (Python)
- **Frontend**: Next.js (React), Tailwind CSS, shadcn/ui
- **Data**: Pandas, Recharts

## Features
- **Waterfall Visualization**: INA-compliant path from FB/EB limits to India EB-1 supply (with/without Restriction Scenario).
- **Current Policy Mode**: 91-country real restrictions (39-country Proclamation ban + 75-country DOS IV pause). India/China excluded.
- **Maximum Scenario**: Additional hypothetical freeze on top-consuming countries (Philippines, Mexico, etc.) beyond real restrictions.
- **Inventory + Pipeline**: Auto-discovered latest USCIS EB I-485 + I-140 files (drop new eb_inventory_*.xlsx or performance data into data/ — no code change), data-driven dependent multipliers from DHS Yearbook Table 7.
- **PD Predictor**: FY2027 confidence with per-FY supply schedule + backlog_ahead by PD year.
- **VB Forecast**: Month-by-month Visa Bulletin FAD/DOF forecast with confidence bands. Uses 87+ months of historical advancement data, seasonal patterns, and supply-adjusted scaling. Supports EB-1/EB-2/EB-3 with restriction toggle.
- **Legislation Tracker**: Pending immigration bills with what-if scenario projections on backlog clearance.
- **I-485 Flow**: Monthly receipts vs. approvals — tracks whether the I-485 queue is growing or shrinking.
- **I-140 Receipts**: New I-140 filings by country and EB category — models queue growth rate.
- **PERM Pipeline**: DOL Labor Certification data — leading indicator of EB-2/EB-3 I-140 filings.
- **H-1B Demand**: Cap registrations and approvals by country — future demand pressure indicator.
- **Processing Times**: USCIS adjudication speed by service center for EB I-485.
- **CEAC Scheduling**: Real-time consular pipeline activity and NVC wait times.

## INA 201/203 Spillover Flow (Restriction Mode)

```mermaid
graph TD
    A[Family-Based Limit: 226k Floor] --> B{91-Country Restrictions}
    B -->|Restricted Volume| C[Visa Savings]
    B -->|Active Volume| D[Actual FB Usage]
    C --> E[EB Vertical Spillover]
    D --> F{Under 226k?}
    F -->|Yes| E
    E --> G[Final EB-1 Supply]
    G --> H[India EB-1 Priority Date Movement]
```

## Setup & Installation

### Local Development

#### 1. Backend (FastAPI)
```bash
# Install dependencies
pip install -r requirements.txt

# Run API
uvicorn api.main:app --reload
```
Access API docs at `http://localhost:8000/docs`.

#### 2. Frontend (Next.js)
```bash
cd frontend
npm install
npm run dev
```
Access the app at `http://localhost:3000`.

### Docker
1. Build and run:
   ```bash
   docker-compose up --build
   ```
2. Access the app at `http://localhost:3000`.

## Documentation
- [Architecture & Design](docs/ARCHITECTURE.md)
- [Policy & Data Verification](docs/POLICY_VERIFICATION.md) — how to cross-verify and update data, country lists, and legal status
