import streamlit as st
from datetime import datetime
from src.parsers.inventory_parser import InventoryParser
from src.engine.demand import DemandModeler

st.set_page_config(page_title="PD Predictor", layout="wide")

st.title("Priority Date Predictor")
st.markdown("Estimate your approval confidence for Fiscal Year 2027.")

# Load Inventory Data to get current state
inv_parser = InventoryParser("data/eb_inventory_jan_2026.csv")
inv_parser.load_data()
inv_parser.clean()
stats = inv_parser.get_india_eb1_queue()

with st.form("pd_form"):
    pd_input = st.date_input("Your Priority Date", value=datetime(2025, 1, 16))
    burn_rate_input = st.number_input("Projected Monthly Burn Rate", value=2000)
    submit = st.form_submit_button("Predict")

if submit:
    modeler = DemandModeler(stats['total'], burn_rate=burn_rate_input)
    score = modeler.calculate_confidence_score(pd_input, target_fy=2027)
    
    st.header(f"Confidence Score: {score*100:.0f}%")
    
    if score >= 0.9:
        st.success("High Confidence: Your date is likely to be current in FY 2027.")
    elif score >= 0.5:
        st.warning("Medium Confidence: It's a close call. Depends on spillover volume.")
    else:
        st.error("Low Confidence: Based on current inventory, FY 2027 might be out of reach.")

    projected_clearance = modeler.project_clearance_date()
    st.info(f"The current India EB-1 queue (including dependents) is projected to clear by **{projected_clearance.strftime('%B %Y')}** at a burn rate of {burn_rate_input}/month.")
