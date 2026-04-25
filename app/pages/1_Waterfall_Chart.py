import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from src.parsers.dos_parser import DOSParser
from src.engine.redistribution import RedistributionEngine

st.set_page_config(page_title="Waterfall Chart", layout="wide")

st.title("Visa Flow Waterfall Chart")
st.markdown("This chart visualizes the path from the statutory FB limit to the final EB-1 supply.")

# Load Data
dos_df = DOSParser.load_from_directory("data/DOS")
dos_parser = DOSParser("data/DOS") # Dummy instance for logic methods
dos_parser.df = dos_df

# Constants
FB_STATUTORY_LIMIT = 226000
EB_BASE_LIMIT = 140000
EB1_STATUTORY_SHARE = 0.286

# 1. Initial FB Usage
total_fb_usage = dos_parser.get_total_fb_usage()
fb_spillover = max(0, FB_STATUTORY_LIMIT - total_fb_usage)

# 2. 75-Country Freeze Redistribution
restricted = RedistributionEngine.get_default_restricted_list()
engine = RedistributionEngine(restricted)

df_frozen = engine.apply_freeze(dos_parser.df)
savings = engine.calculate_savings(dos_parser.df, df_frozen)

# Calculate Totals
total_eb_supply = EB_BASE_LIMIT + fb_spillover + savings
eb1_supply = int(total_eb_supply * EB1_STATUTORY_SHARE)

# Waterfall Data
x = ["EB Base Limit", "FB Spillover", "Redistribution Savings", "Total EB Supply", "EB-1 Share (28.6%)"]
y = [EB_BASE_LIMIT, fb_spillover, savings, total_eb_supply, eb1_supply]
measure = ["relative", "relative", "relative", "total", "total"]

fig = go.Figure(go.Waterfall(
    name = "Spillover", orientation = "v",
    measure = measure,
    x = x,
    textposition = "outside",
    text = [f"{val:,.0f}" for val in y],
    y = [EB_BASE_LIMIT, fb_spillover, savings, 0, eb1_supply], # Use 0 for 'Total EB Supply' to show it as a total bar
    connector = {"line":{"color":"rgb(63, 63, 63)"}},
))

# Adjusting y for the 'total' measure of 'Total EB Supply'
# Waterfall tool in plotly: if measure is 'total', the value in y is ignored and it sums preceding relatives.
# But for 'EB-1 Share', we want to show it as a final total bar of a specific value.
fig.data[0].y = [EB_BASE_LIMIT, fb_spillover, savings, 0, eb1_supply]
fig.data[0].measure = ["relative", "relative", "relative", "total", "absolute"] # 'absolute' shows the value as a bar from 0

fig.update_layout(
        title = "FY 2026/2027 Spillover Path (INA 201/203 compliant)",
        showlegend = True
)

st.plotly_chart(fig, use_container_width=True)

st.info(f"Total redistributed savings from restricted countries: {savings:,.0f} visas.")
