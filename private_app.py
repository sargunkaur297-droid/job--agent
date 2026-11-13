"""Authenticated entry point for the personal Job Agent dashboard.

Deploy this file as a separate, private Streamlit app. Keep streamlit_app.py
as the public portfolio demo entry point.
"""
from __future__ import annotations

import os
import runpy

import streamlit as st

st.set_page_config(page_title="My Job Agent", page_icon="🎯", layout="wide")

st.title("🎯 Personal Job Agent")

# Streamlit's OIDC login authenticates the person opening this app.
if not st.user.is_logged_in:
    st.write("Sign in with your Google account to open your private job-search dashboard.")
    st.login()
    st.stop()

allowed_email = str(st.secrets.get("private", {}).get("allowed_email", "")).strip().lower()
signed_in_email = str(st.user.get("email", "")).strip().lower()

if not allowed_email:
    st.error("Private access is not configured yet. Add [private].allowed_email to Streamlit secrets.")
    st.stop()

if not signed_in_email or signed_in_email != allowed_email:
    st.error("This dashboard is restricted to its owner. Sign out and use the authorised Google account.")
    st.button("Sign out", on_click=st.logout)
    st.stop()

db_url = str(st.secrets.get("database", {}).get("url", "")).strip()
if not db_url:
    st.error("Database is not configured. Add [database].url to Streamlit secrets.")
    st.stop()
os.environ["JOB_AGENT_DATABASE_URL"] = db_url

# dashboard.py remains directly runnable locally. This flag prevents it from
# attempting to set page configuration a second time when loaded here.
os.environ["JOB_AGENT_AUTHENTICATED"] = "1"
runpy.run_path("dashboard.py", run_name="__main__")
