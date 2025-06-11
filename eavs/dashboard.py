from tarfile import data_filter

import pandas as pd
import streamlit as st
from plotly import express as px, graph_objects as go
from pathlib import Path

from eavs.config import RAW_DATA_DIR, INTERIM_DATA_DIR

datasets = {
    "2022": pd.read_csv(INTERIM_DATA_DIR / "eavs_2022.csv", dtype_backend="pyarrow")
}

st.set_page_config(
    page_title="EAVS Dashboard",
    layout="wide",
    initial_sidebar_state="expanded")

datasets["2022"] = datasets["2022"].sort_values(by="Reject_%")

st.bar_chart(data=datasets["2022"], x="State_Full", y="Reject_%", color="#0000FF")

with st.sidebar:
    st.title('EAVS Data Dashboard')

    year_list = datasets.keys()

    selected_year = st.selectbox('Select a year:', year_list)

    compare_to = st.selectbox('Compare to year:', year_list)