import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
from datetime import datetime
from src.parsers.inventory_parser import InventoryParser
from src.parsers.pipeline_parser import PipelineParser
from src.engine.demand import DemandModeler

st.set_page_config(page_title="PD Predictor", layout="wide")

st.title("Priority Date Predictor")
st.markdown("Estimate your approval confidence for Fiscal Year 2027.")

# Load Combined Data
inv_parser = InventoryParser("data/eb_inventory_january_2026.xlsx")
inv_stats_total = inv_parser.get_india_eb1_queue() # Total queue

pipe_parser = PipelineParser("data/eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx")
pipe_parser.load_data()
pipe_total = pipe_parser.get_india_eb1_backlog() # Multiplier already applied

total_queue = inv_stats_total['total'] + pipe_total

with st.form("pd_form"):
    pd_input = st.date_input("Your Priority Date", value=datetime(2025, 1, 16))
    burn_rate_input = st.number_input("Projected Monthly Burn Rate", value=2000)
    submit = st.form_submit_button("Predict")

if submit:
    # Calculate backlog ahead of this PD
    # We use the inventory parser to find how many are before the input PD
    inv_ahead = inv_parser.get_india_eb1_queue(cutoff_month=pd_input.month, cutoff_year=pd_input.year)
    
    # If PD is after 2023 (end of inventory), we add some pipeline estimate
    # Simple heuristic: if PD is 2024 or 2025, they are likely in the 'Pipeline'
    if pd_input.year > 2023:
        # Roughly: all of inventory + a fraction of pipeline
        # (Assuming pipeline is roughly 2024-2025)
        months_into_pipeline = (pd_input.year - 2024) * 12 + pd_input.month
        pipeline_fraction = min(1.0, months_into_pipeline / 24.0) # Assume 2 year pipeline
        backlog_ahead = inv_stats_total['total'] + int(pipe_total * pipeline_fraction)
    else:
        backlog_ahead = inv_ahead['total']

    modeler = DemandModeler(total_queue, burn_rate=burn_rate_input)
    score = modeler.calculate_confidence_score(pd_input, backlog_ahead=backlog_ahead, target_fy=2027)
    
    st.header(f"Confidence Score: {score*100:.0f}%")
    st.write(f"**Backlog ahead of you (estimated):** {backlog_ahead:,}")

    projected_clearance = modeler.project_clearance_date()
    st.info(f"The total India EB-1 queue (Inventory + Pipeline) is projected to clear by **{projected_clearance.strftime('%B %Y')}** at a burn rate of {burn_rate_input}/month.")
