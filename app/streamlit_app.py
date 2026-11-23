"""
CardioStage Streamlit app: entry point and page navigation.

Run from the project root:
    streamlit run app/streamlit_app.py

st.navigation gives each page a proper title and icon in the sidebar
(instead of file names) and lets us configure the page once, here.
"""

import streamlit as st

from consent import require_consent

st.set_page_config(page_title="CardioStage", page_icon="🫀", layout="wide")

# Security (SEC-03): never show tracebacks to visitors. .streamlit/config.toml
# already says "none", but Streamlit Community Cloud overrides that file with
# `false`, which in this Streamlit version means "stacktrace". The option is
# scriptable, so setting it here wins in every environment.
st.set_option("client.showErrorDetails", "none")

# Nothing else runs until the visitor has read and accepted the notice.
require_consent()

navigation = st.navigation(
    [
        st.Page("views/screener.py", title="Screener", icon="🫀", default=True),
        st.Page("views/results.py", title="Results", icon="📊"),
        st.Page("views/about.py", title="About", icon="ℹ️"),
    ]
)
navigation.run()
