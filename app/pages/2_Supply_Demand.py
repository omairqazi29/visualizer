import streamlit as st
import plotly.express as px
import pandas as pd
from src.parsers.inventory_parser import InventoryParser
from src.engine.demand import DemandModeler

st.set_page_config(page_title="Supply/Demand", layout="wide")

st.title("Supply/Demand Curve: India EB-1")

# Load Inventory Data
inv_parser = InventoryParser("data/eb_inventory_jan_2026.csv")
inv_parser.load_data()
inv_parser.clean()

stats = inv_parser.get_india_eb1_queue()

st.subheader("Inventory Breakdown (incl. 2.2x Multiplier)")
col1, col2, col3 = st.columns(3)
col1.metric("Mountain (Pre-Apr 2023)", f"{stats['mountain']:,}")
col2.metric("Valley (Apr-Dec 2023)", f"{stats['valley']:,}")
col3.metric("Total Queue", f"{stats['total']:,}")

# Burn Rate Projection
burn_rate = st.slider("Monthly Visa Burn Rate", 500, 5000, 2000)
modeler = DemandModeler(stats['total'], burn_rate=burn_rate)

# Create a projection dataframe
months = []
remaining_queue = []
current_queue = stats['total']

for i in range(24): # 2 years projection
    months.append(i)
    remaining_queue.append(max(0, current_queue))
    current_queue -= burn_rate

projection_df = pd.DataFrame({
    "Month": months,
    "Remaining Queue": remaining_queue
})

fig = px.area(projection_df, x="Month", y="Remaining Queue", 
             title=f"Projected India EB-1 Queue Clearance (@ {burn_rate}/month)")
st.plotly_chart(fig, use_container_width=True)

projected_date = modeler.project_clearance_date()
st.success(f"Estimated Clearance Date for current inventory: **{projected_date.strftime('%B %Y')}**")
