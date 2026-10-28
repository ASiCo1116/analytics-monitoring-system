"""Server entry point: `streamlit run server.py`.

Runs the app (app.py) together with the routes that set and delete the
login cookie (lib/login_cookie.py).
"""

import streamlit as st

from lib.login_cookie import routes

app = st.App("app.py", routes=routes)
