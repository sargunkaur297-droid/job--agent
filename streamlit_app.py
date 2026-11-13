"""Public, read-only Streamlit demo for the Job Agent portfolio.

This entry point uses bundled synthetic emails and an in-memory SQLite database.
It never connects to Gmail, reads a personal resume, or writes user data to disk.
Run locally with: streamlit run streamlit_app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import db
from app.config import load_config
from app.demo import demo_messages
from app.matcher import LocalMatcher
from app.pipeline import run_pipeline


st.set_page_config(page_title="Job Agent | Demo", page_icon="🎯", layout="wide")


@st.cache_resource
def load_demo_data():
    """Create a process-local demo database; it is discarded when the app restarts."""
    conn = db.connect(":memory:")
    cfg = load_config()
    cfg["verification"]["fetch_pages"] = False
    cfg["filters"]["date_policy"] = "allow_hints"
    run_pipeline(
        conn,
        cfg,
        messages_by_source=demo_messages(),
        matcher=LocalMatcher(cfg),
        notify_email=False,
        sleep=False,
    )
    return conn


st.title("🎯 Job Agent")
st.caption("A portfolio demo of an AI-assisted job-alert screening and application-tracking workflow.")

st.info(
    "Demo mode — this page uses fictional sample job-alert emails only. "
    "It does not connect to Gmail, use a personal resume, send email, or save personal data. "
    "The in-memory sample database resets when the app restarts."
)

conn = load_demo_data()
df = pd.read_sql_query(
    """
    SELECT title, company, location, sources, posted_hint, filter_status,
           filter_reason, url, description
    FROM jobs
    ORDER BY CASE filter_status WHEN 'accepted' THEN 0 ELSE 1 END, title
    """,
    conn,
)

if df.empty:
    st.warning("The bundled sample data did not produce any job records.")
    st.stop()

accepted = df[df["filter_status"] == "accepted"]
rejected = df[df["filter_status"] == "rejected"]

m1, m2, m3 = st.columns(3)
m1.metric("Sample jobs processed", len(df))
m2.metric("Passed filters", len(accepted))
m3.metric("Filtered out", len(rejected))

st.subheader("Explore sample jobs")
left, right = st.columns([1, 2])
with left:
    status_filter = st.selectbox("Filter result", ["All", "Passed filters", "Filtered out"])
    source_options = sorted({s for value in df["sources"].fillna("") for s in value.split(",") if s})
    selected_sources = st.multiselect("Source", source_options, default=source_options)
    search = st.text_input("Search role or company")

view = df.copy()
if status_filter == "Passed filters":
    view = view[view["filter_status"] == "accepted"]
elif status_filter == "Filtered out":
    view = view[view["filter_status"] == "rejected"]
view = view[
    view["sources"].fillna("").apply(
        lambda value: any(source in selected_sources for source in value.split(","))
    )
]
if search.strip():
    needle = search.strip().lower()
    view = view[
        view["title"].str.lower().str.contains(needle, na=False)
        | view["company"].str.lower().str.contains(needle, na=False)
    ]

with right:
    st.dataframe(
        view[["title", "company", "location", "sources", "posted_hint", "filter_status"]]
        .rename(columns={
            "posted_hint": "Posted",
            "filter_status": "Filter result",
            "sources": "Source",
        }),
        use_container_width=True,
        hide_index=True,
    )

st.caption(
    "The sample listings and company names are illustrative. Their external links are not live job vacancies."
)

with st.expander("What happens in the pipeline"):
    st.markdown(
        """
        1. **Ingest** — read sample alert emails in Indeed, LinkedIn and Naukri formats.
        2. **Parse and normalise** — extract role, company, location and listing details.
        3. **Deduplicate** — merge repeated listings from different sources.
        4. **Filter** — apply role, location, experience and posting-age rules.
        5. **Review** — display the resulting shortlist for a person to assess.

        The full local application also supports Gmail OAuth, optional Gemini scoring,
        a persistent local SQLite tracker and digest emails. Those personal-account
        features are deliberately not enabled in this public demo.
        """
    )

st.subheader("Filter decisions")
if not rejected.empty:
    st.dataframe(
        rejected[["title", "company", "filter_reason"]].rename(
            columns={"filter_reason": "Reason"}
        ),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.success("All sample jobs passed the current filters.")
