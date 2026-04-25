import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

import streamlit as st

st.set_page_config(
    page_title="The Spillover Engine",
    page_icon="📈",
    layout="wide"
)

st.title("The Spillover Engine 📈")

st.markdown("""
### Predicting the Impact of 2026/2027 U.S. Immigrant Visa Restrictions

Welcome to **The Spillover Engine**, a production-grade visualization and prediction platform 
designed to analyze the India EB-1 backlog under the latest Department of State (DOS) and USCIS data.

#### Key Features:
- **INA-Logic Spillover**: Visualizes the flow from Family-Based (FB) statutory limits through the '75-Country Freeze' to find the final EB-1 supply.
- **Mountain vs. Valley Analysis**: A deep dive into the India EB-1 inventory, highlighting the massive concentration of applicants before April 2023.
- **Comprehensive Queue Tracking**: Combines pending I-485 adjustment of status applications with the approved I-140 pipeline awaiting visa availability.
- **Priority Date Predictor**: Provides confidence scores for approval in FY 2027 based on user-inputted burn rates and priority dates.

#### Data Sources:
This application is powered by:
- **DOS Monthly Issuances**: Full FY2025 sequence (Oct 2024 - Sep 2025).
- **USCIS EB Inventory**: As of January 2026.
- **USCIS Performance Data**: Approved I-140 petitions as of FY2025 Q4.

*Navigate using the sidebar to explore the visualizations.*
""")

st.sidebar.info("Select a visualization above to begin.")
