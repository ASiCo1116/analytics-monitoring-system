"""Server entry point: `streamlit run server.py`.

Runs the app (app.py) together with the routes that set and delete the
login cookie (lib/login_cookie.py).
"""

# Imported once here, at start-up, before any session runs. Plotly looks
# numpy and pandas up in sys.modules without importing them, so a chart
# drawn while another session thread is still importing them for the first
# time finds a half-initialized module ("partially initialized module
# 'pandas' has no attribute 'Series'"). Slow first imports (e.g. macOS
# checking library signatures) make that window wide.
import numpy  # noqa: F401
import pandas  # noqa: F401
import streamlit as st

from lib.login_cookie import routes

app = st.App("app.py", routes=routes)
