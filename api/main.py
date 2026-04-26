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
async def get_waterfall_data():
    try:
        dos_df = DOSParser.load_from_directory("data/DOS")
        dos_parser = DOSParser("data/DOS")
        dos_parser.df = dos_df

        total_fb_usage = dos_parser.get_total_fb_usage()
        fb_spillover = max(0, FB_STATUTORY_LIMIT - total_fb_usage)

        restricted = RedistributionEngine.get_default_restricted_list()
        engine = RedistributionEngine(restricted)
        df_frozen = engine.apply_freeze(dos_parser.df)
        savings = engine.calculate_savings(dos_parser.df, df_frozen)

        total_eb_supply = EB_BASE_LIMIT + fb_spillover + savings
        eb1_supply = int(total_eb_supply * EB1_STATUTORY_SHARE)

        return {
            "eb_base_limit": int(EB_BASE_LIMIT),
            "fb_spillover": int(fb_spillover),
            "redistribution_savings": int(savings),
            "total_eb_supply": int(total_eb_supply),
            "eb1_supply": int(eb1_supply)
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

        # 2. Calculate Dynamic Annual Supply (Volume)
        total_fb_usage = dos_parser.get_total_fb_usage()
        fb_spillover = max(0, FB_STATUTORY_LIMIT - total_fb_usage)

        savings = 0
        if apply_freeze:
            restricted = RedistributionEngine.get_default_restricted_list()
            engine = RedistributionEngine(restricted)
            df_frozen = engine.apply_freeze(dos_parser.df)
            savings = engine.calculate_savings(dos_parser.df, df_frozen)

        total_eb_supply = EB_BASE_LIMIT + fb_spillover + savings
        eb1_supply = int(total_eb_supply * EB1_STATUTORY_SHARE)

        # 3. Project Trajectory
        modeler = DemandModeler(total_queue, eb1_supply, monthly_dist)
        projection = modeler.project_clearance()

        return {
            "inventory": {k: int(v) for k, v in inv_stats.items()},
            "pipeline_total": int(pipe_total),
            "total_queue": total_queue,
            "annual_eb1_supply": eb1_supply,
            "clearance_date": projection["clearance_date"].strftime("%Y-%m-%d"),
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

        # 2. Calculate Dynamic Annual Supply (Volume)
        total_fb_usage = dos_parser.get_total_fb_usage()
        fb_spillover = max(0, FB_STATUTORY_LIMIT - total_fb_usage)

        savings = 0
        if apply_freeze:
            restricted = RedistributionEngine.get_default_restricted_list()
            engine = RedistributionEngine(restricted)
            df_frozen = engine.apply_freeze(dos_parser.df)
            savings = engine.calculate_savings(dos_parser.df, df_frozen)

        total_eb_supply = EB_BASE_LIMIT + fb_spillover + savings
        eb1_supply = int(total_eb_supply * EB1_STATUTORY_SHARE)

        modeler = DemandModeler(total_queue, eb1_supply, monthly_dist)
        score = modeler.calculate_confidence_score(pd_dt, backlog_ahead=backlog_ahead, target_fy=2027)
        projection = modeler.project_clearance(backlog=backlog_ahead)

        return {
            "confidence_score": float(score),
            "backlog_ahead": int(backlog_ahead),
            "total_queue": int(total_queue),
            "annual_eb1_supply": eb1_supply,
            "projected_clearance_date": projection["clearance_date"].strftime("%Y-%m-%d"),
            "trajectory": projection["trajectory"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
