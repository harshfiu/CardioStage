"""
CardioStage Streamlit app: entry point and page navigation.

Run from the project root:
    streamlit run app/streamlit_app.py

st.navigation gives each page a proper title and icon in the sidebar
(instead of file names) and lets us configure the page once, here.
"""

import streamlit as st

st.set_page_config(page_title="CardioStage", page_icon="🫀", layout="wide")

navigation = st.navigation([
    st.Page("views/screener.py", title="Screener", icon="🫀", default=True),
    st.Page("views/results.py", title="Results", icon="📊"),
    st.Page("views/about.py", title="About", icon="ℹ️"),
])
navigation.run()
