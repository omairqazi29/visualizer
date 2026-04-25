import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
import plotly.express as px
import pandas as pd
from src.parsers.inventory_parser import InventoryParser
from src.parsers.pipeline_parser import PipelineParser
from src.engine.demand import DemandModeler

st.set_page_config(page_title="Supply/Demand", layout="wide")

st.title("Supply/Demand Curve: India EB-1")

# Load Inventory Data (Pending I-485)
inv_parser = InventoryParser("data/eb_inventory_january_2026.xlsx")
inv_stats = inv_parser.get_india_eb1_queue()

# Load Pipeline Data (Approved I-140 awaiting visa)
pipe_parser = PipelineParser("data/eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx")
pipe_parser.load_data()
pipe_total = pipe_parser.get_india_eb1_backlog() # Multiplier already applied in parser

total_queue = inv_stats['total'] + pipe_total

st.subheader("Comprehensive India EB-1 Queue Breakdown")
col1, col2, col3, col4 = st.columns(4)
col1.metric("I-485 Inventory", f"{inv_stats['total']:,}")
col2.metric("I-140 Pipeline (est.)", f"{pipe_total:,}")
col3.metric("Total Queue", f"{total_queue:,}")
col4.metric("Burn Rate", "2,000/mo")

# Load DOS Data for Burn Rate calculation
dos_df = DOSParser.load_from_directory("data/DOS")
# Assume 12 months of data in the directory for simple average
dynamic_burn_rate = DemandModeler.calculate_burn_rate_from_dos(dos_df, months=12)

# Details
with st.expander("See Inventory Details"):
    st.write(f"**Mountain (Pre-Apr 2023):** {inv_stats['mountain']:,}")
    st.write(f"**Valley (Apr-Dec 2023):** {inv_stats['valley']:,}")
    st.write(f"**I-140 Backlog (Incl. Dependents):** {pipe_total:,}")

# Burn Rate Projection
burn_rate = st.slider("Monthly Visa Burn Rate", 500, 5000, dynamic_burn_rate)
modeler = DemandModeler(total_queue, burn_rate=burn_rate)

# Create a projection dataframe
months = []
remaining_queue = []
current_queue = total_queue

for i in range(36): # 3 years projection
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
st.success(f"Estimated Clearance Date for total queue: **{projected_date.strftime('%B %Y')}**")
