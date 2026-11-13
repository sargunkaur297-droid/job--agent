"""Password-gated entry point for the personal Job Agent dashboard.

Keep streamlit_app.py as the separate public portfolio demo entry point.
"""
from __future__ import annotations

import hmac
import os
import runpy

import streamlit as st

st.set_page_config(page_title="My Job Agent", page_icon="🎯", layout="wide")

st.title("🎯 Personal Job Agent")

# A single owner password is stored in Streamlit Secrets.
# Authentication is kept in this Streamlit session only.
expected_password = str(st.secrets.get("private", {}).get("password", ""))

if not expected_password:
    st.error("Set [private].password in this app's Streamlit Secrets before continuing.")
    st.stop()

if not st.session_state.get("job_agent_authenticated", False):
    st.write("Enter your private dashboard password.")
    with st.form("job_agent_login"):
        entered_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        if hmac.compare_digest(entered_password, expected_password):
            st.session_state["job_agent_authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

if st.sidebar.button("Log out"):
    st.session_state["job_agent_authenticated"] = False
    st.rerun()

db_url = str(st.secrets.get("database", {}).get("url", "")).strip()
if not db_url:
    st.error("Database is not configured. Add [database].url to Streamlit Secrets.")
    st.stop()
os.environ["JOB_AGENT_DATABASE_URL"] = db_url

# Prevent dashboard.py from setting page configuration a second time.
os.environ["JOB_AGENT_AUTHENTICATED"] = "1"
runpy.run_path("dashboard.py", run_name="__main__")
