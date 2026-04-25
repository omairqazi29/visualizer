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
inv_stats = inv_parser.get_india_eb1_queue()

pipe_parser = PipelineParser("data/eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx")
pipe_parser.load_data()
pipe_total = int(pipe_parser.get_india_eb1_backlog() * 2.2)

total_queue = inv_stats['total'] + pipe_total

with st.form("pd_form"):
    pd_input = st.date_input("Your Priority Date", value=datetime(2025, 1, 16))
    burn_rate_input = st.number_input("Projected Monthly Burn Rate", value=2000)
    submit = st.form_submit_button("Predict")

if submit:
    modeler = DemandModeler(total_queue, burn_rate=burn_rate_input)
    score = modeler.calculate_confidence_score(pd_input, target_fy=2027)
    
    st.header(f"Confidence Score: {score*100:.0f}%")
    
    if score >= 0.9:
        st.success("High Confidence: Your date is likely to be current in FY 2027.")
    elif score >= 0.5:
        st.warning("Medium Confidence: It's a close call. Depends on spillover volume.")
    else:
        st.error("Low Confidence: Based on current inventory + pipeline, FY 2027 might be out of reach.")

    projected_clearance = modeler.project_clearance_date()
    st.info(f"The total India EB-1 queue (Inventory + Pipeline) is projected to clear by **{projected_clearance.strftime('%B %Y')}** at a burn rate of {burn_rate_input}/month.")
