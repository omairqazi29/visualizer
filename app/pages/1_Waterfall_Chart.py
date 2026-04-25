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

# 1. Initial FB Usage
total_fb_usage = dos_parser.get_total_fb_usage()

# 2. 75-Country Freeze Redistribution
restricted = RedistributionEngine.get_default_restricted_list()
engine = RedistributionEngine(restricted)

df_frozen = engine.apply_freeze(dos_parser.df)
savings = engine.calculate_savings(dos_parser.df, df_frozen)

# Waterfall Data
x = ["FB Statutory Limit", "Actual FB Usage", "Banned Country Savings", "Final EB-1 Supply"]
y = [FB_STATUTORY_LIMIT, -total_fb_usage, savings, 0] # Last is calculated
measure = ["relative", "relative", "relative", "total"]

fig = go.Figure(go.Waterfall(
    name = "Spillover", orientation = "v",
    measure = measure,
    x = x,
    textposition = "outside",
    text = [f"{val:,.0f}" if val !=0 else "" for val in y],
    y = y,
    connector = {"line":{"color":"rgb(63, 63, 63)"}},
))

fig.update_layout(
        title = "FY 2026/2027 Spillover Path",
        showlegend = True
)

st.plotly_chart(fig, use_container_width=True)

st.info(f"Total redistributed savings from restricted countries: {savings:,.0f} visas.")
