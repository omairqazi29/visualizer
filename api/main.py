import sys
import os
from datetime import datetime
from typing import Optional

# Add the project root to sys.path to import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.parsers.dos_parser import DOSParser
from src.parsers.inventory_parser import InventoryParser
from src.parsers.pipeline_parser import PipelineParser
from src.engine.redistribution import RedistributionEngine
from src.engine.demand import DemandModeler

app = FastAPI(title="The Spillover Engine API")

# Enable CORS for Next.js development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
FB_STATUTORY_LIMIT = 226000
EB_BASE_LIMIT = 140000
EB1_STATUTORY_SHARE = 0.286

@app.get("/api/waterfall")
async def get_waterfall_data(apply_freeze: bool = False):
    try:
        dos_df = DOSParser.load_from_directory("data/DOS")
        dos_parser = DOSParser("data/DOS")
        dos_parser.df = dos_df

        # 1. Base EB Limit
        eb_base = EB_BASE_LIMIT
        
        # 2. Standard FB Spillover
        total_fb_usage = dos_parser.get_total_fb_usage()
        standard_fb_spillover = max(0, FB_STATUTORY_LIMIT - total_fb_usage)

        # 3. Restriction Windfall (Trump Effect)
        # Visas from restricted countries that are banned/frozen
        fb_savings = 0
        eb45_savings = 0
        
        if apply_freeze:
            restricted = RedistributionEngine.get_default_restricted_list()
            engine = RedistributionEngine(restricted)
            
            # FB Savings (Spills to EB 1, 2, 3)
            fb_df = dos_parser.df[dos_parser.df['visa_category'].isin(DOSParser.FB_CATEGORIES)]
            fb_frozen = engine.apply_freeze(fb_df)
            fb_savings = engine.calculate_savings(fb_df, fb_frozen)
            
            # EB4/5 Savings (Spills ONLY to EB-1)
            # EB4 codes: SD, SE, SI, SK, SQ, SR, SU, SW
            # EB5 codes: C5, I5, R5, T5
            eb45_cats = ['SD', 'SE', 'SI1', 'SI2', 'SI3', 'SK', 'SQ1', 'SQ2', 'SQ3', 'SR', 'SU', 'SW', 'C5', 'I5', 'R5', 'T5']
            eb45_df = dos_parser.df[dos_parser.df['visa_category'].isin(eb45_cats)]
            eb45_frozen = engine.apply_freeze(eb45_df)
            eb45_savings = engine.calculate_savings(eb45_df, eb45_frozen)

        # Total EB Supply (used for sharing between 1, 2, 3)
        # Note: Unused EB4/5 from normal operations (non-freeze) also exists
        eb45_cats = ['SD', 'SE', 'SI1', 'SI2', 'SI3', 'SK', 'SQ1', 'SQ2', 'SQ3', 'SR', 'SU', 'SW', 'C5', 'I5', 'R5', 'T5']
        eb45_usage = dos_parser.df[dos_parser.df['visa_category'].isin(eb45_cats)]['count'].sum()
        eb45_statutory = int(EB_BASE_LIMIT * 0.142) # 7.1% + 7.1%
        standard_eb45_spillover = max(0, eb45_statutory - eb45_usage)

        total_shared_supply = eb_base + standard_fb_spillover + fb_savings
        eb1_statutory_share = int(total_shared_supply * EB1_STATUTORY_SHARE)
        
        # INA 203(b)(1): EB1 gets its share + ANY unused EB4 and EB5
        total_eb1_supply = eb1_statutory_share + standard_eb45_spillover + eb45_savings

        return {
            "eb_base_limit": int(eb_base),
            "fb_spillover_std": int(standard_fb_spillover),
            "fb_savings_freeze": int(fb_savings),
            "eb45_spillover_std": int(standard_eb45_spillover),
            "eb45_savings_freeze": int(eb45_savings),
            "total_eb_supply": int(total_shared_supply + standard_eb45_spillover + eb45_savings),
            "eb1_supply": int(total_eb1_supply)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/supply-demand")
async def get_supply_demand_data(apply_freeze: bool = False):
    try:
        # Load Inventory Data
        inv_parser = InventoryParser("data/eb_inventory_january_2026.xlsx")
        inv_stats = inv_parser.get_india_eb1_queue()

        # Load Pipeline Data
        pipe_parser = PipelineParser("data/eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx")
        pipe_parser.load_data()
        pipe_total = pipe_parser.get_india_eb1_backlog()
        
        total_queue = int(inv_stats['total'] + pipe_total)

        # Load DOS for historical distribution and supply calculations
        dos_df = DOSParser.load_from_directory("data/DOS")
        dos_parser = DOSParser("data/DOS")
        dos_parser.df = dos_df
        
        # 1. Calculate Monthly Distribution (Seasonality)
        monthly_dist = dos_parser.get_monthly_distribution(
            country="India", 
            categories=["E11", "E12", "E13"]
        )

        # Calculate Dynamic Annual Supply (Volume)
        total_fb_usage = dos_parser.get_total_fb_usage()
        standard_fb_spillover = max(0, FB_STATUTORY_LIMIT - total_fb_usage)

        fb_savings = 0
        eb45_savings = 0
        if apply_freeze:
            restricted = RedistributionEngine.get_default_restricted_list()
            engine = RedistributionEngine(restricted)
            fb_df = dos_parser.df[dos_parser.df['visa_category'].isin(DOSParser.FB_CATEGORIES)]
            fb_savings = engine.calculate_savings(fb_df, engine.apply_freeze(fb_df))
            
            eb45_cats = ['SD', 'SE', 'SI1', 'SI2', 'SI3', 'SK', 'SQ1', 'SQ2', 'SQ3', 'SR', 'SU', 'SW', 'C5', 'I5', 'R5', 'T5']
            eb45_df = dos_parser.df[dos_parser.df['visa_category'].isin(eb45_cats)]
            eb45_savings = engine.calculate_savings(eb45_df, engine.apply_freeze(eb45_df))

        eb45_cats = ['SD', 'SE', 'SI1', 'SI2', 'SI3', 'SK', 'SQ1', 'SQ2', 'SQ3', 'SR', 'SU', 'SW', 'C5', 'I5', 'R5', 'T5']
        eb45_usage = dos_parser.df[dos_parser.df['visa_category'].isin(eb45_cats)]['count'].sum()
        eb45_statutory = int(EB_BASE_LIMIT * 0.142)
        standard_eb45_spillover = max(0, eb45_statutory - eb45_usage)

        total_shared_supply = EB_BASE_LIMIT + standard_fb_spillover + fb_savings
        global_eb1_supply = int(total_shared_supply * EB1_STATUTORY_SHARE) + standard_eb45_spillover + eb45_savings

        if not apply_freeze:
            # Historically, India gets around 9k EB1s a year (share + surplus).
            india_eb1_supply = 9000
        else:
            # Calculate windfall for the 'Trump effect' (Freeze Mode)
            eb1_cats = ['E11', 'E12', 'E13', 'E1', 'IB1', 'IB2']
            row_eb1_usage = dos_parser.df[
                (~dos_parser.df['chargeability'].str.contains('India', case=False, na=False)) & 
                (dos_parser.df['visa_category'].isin(eb1_cats))
            ]['count'].sum()
            
            india_eb1_supply = max(0, global_eb1_supply - row_eb1_usage)

        # 3. Project Trajectory using India-only supply
        modeler = DemandModeler(total_queue, int(india_eb1_supply), monthly_dist)
        projection = modeler.project_clearance()

        return {
            "inventory": {k: int(v) for k, v in inv_stats.items()},
            "pipeline_total": int(pipe_total),
            "total_queue": int(total_queue),
            "annual_eb1_supply": int(india_eb1_supply),
            "clearance_date": projection["clearance_date"].strftime("%Y-%m-%d"),
            "months_to_clear": int(projection["months_to_clear"]),
            "trajectory": projection["trajectory"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/predict")
async def predict_pd(priority_date: str, apply_freeze: bool = False):
    try:
        pd_dt = datetime.strptime(priority_date, "%Y-%m-%d")
        
        inv_parser = InventoryParser("data/eb_inventory_january_2026.xlsx")
        inv_stats_total = inv_parser.get_india_eb1_queue()

        pipe_parser = PipelineParser("data/eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx")
        pipe_parser.load_data()
        pipe_total = pipe_parser.get_india_eb1_backlog()

        total_queue = inv_stats_total['total'] + pipe_total

        inv_ahead = inv_parser.get_india_eb1_queue(cutoff_month=pd_dt.month, cutoff_year=pd_dt.year)
        
        if pd_dt.year > 2023:
            months_into_pipeline = (pd_dt.year - 2024) * 12 + pd_dt.month
            pipeline_fraction = min(1.0, months_into_pipeline / 24.0)
            backlog_ahead = inv_stats_total['total'] + int(pipe_total * pipeline_fraction)
        else:
            backlog_ahead = inv_ahead['total']

        # Load DOS for historical distribution and supply calculations
        dos_df = DOSParser.load_from_directory("data/DOS")
        dos_parser = DOSParser("data/DOS")
        dos_parser.df = dos_df
        
        # 1. Calculate Monthly Distribution (Seasonality)
        monthly_dist = dos_parser.get_monthly_distribution(
            country="India", 
            categories=["E11", "E12", "E13"]
        )

        # Calculate Dynamic Annual Supply (Volume)
        total_fb_usage = dos_parser.get_total_fb_usage()
        standard_fb_spillover = max(0, FB_STATUTORY_LIMIT - total_fb_usage)

        fb_savings = 0
        eb45_savings = 0
        if apply_freeze:
            restricted = RedistributionEngine.get_default_restricted_list()
            engine = RedistributionEngine(restricted)
            fb_df = dos_parser.df[dos_parser.df['visa_category'].isin(DOSParser.FB_CATEGORIES)]
            fb_savings = engine.calculate_savings(fb_df, engine.apply_freeze(fb_df))
            
            eb45_cats = ['SD', 'SE', 'SI1', 'SI2', 'SI3', 'SK', 'SQ1', 'SQ2', 'SQ3', 'SR', 'SU', 'SW', 'C5', 'I5', 'R5', 'T5']
            eb45_df = dos_parser.df[dos_parser.df['visa_category'].isin(eb45_cats)]
            eb45_savings = engine.calculate_savings(eb45_df, engine.apply_freeze(eb45_df))

        eb45_cats = ['SD', 'SE', 'SI1', 'SI2', 'SI3', 'SK', 'SQ1', 'SQ2', 'SQ3', 'SR', 'SU', 'SW', 'C5', 'I5', 'R5', 'T5']
        eb45_usage = dos_parser.df[dos_parser.df['visa_category'].isin(eb45_cats)]['count'].sum()
        eb45_statutory = int(EB_BASE_LIMIT * 0.142)
        standard_eb45_spillover = max(0, eb45_statutory - eb45_usage)

        total_shared_supply = EB_BASE_LIMIT + standard_fb_spillover + fb_savings
        global_eb1_supply = int(total_shared_supply * EB1_STATUTORY_SHARE) + standard_eb45_spillover + eb45_savings

        if not apply_freeze:
            # Historically, India gets around 9k EB1s a year (share + surplus).
            india_eb1_supply = 9000
        else:
            # Calculate windfall for the 'Trump effect' (Freeze Mode)
            eb1_cats = ['E11', 'E12', 'E13', 'E1', 'IB1', 'IB2']
            row_eb1_usage = dos_parser.df[
                (~dos_parser.df['chargeability'].str.contains('India', case=False, na=False)) & 
                (dos_parser.df['visa_category'].isin(eb1_cats))
            ]['count'].sum()
            
            india_eb1_supply = max(0, global_eb1_supply - row_eb1_usage)

        modeler = DemandModeler(total_queue, int(india_eb1_supply), monthly_dist)
        score = modeler.calculate_confidence_score(pd_dt, backlog_ahead=backlog_ahead, target_fy=2027)
        projection = modeler.project_clearance(backlog=backlog_ahead)

        return {
            "confidence_score": float(score),
            "backlog_ahead": int(backlog_ahead),
            "total_queue": int(total_queue),
            "annual_eb1_supply": int(india_eb1_supply),
            "projected_clearance_date": projection["clearance_date"].strftime("%Y-%m-%d"),
            "months_to_clear": int(projection["months_to_clear"]),
            "trajectory": projection["trajectory"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
