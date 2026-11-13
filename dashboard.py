"""Streamlit dashboard:  streamlit run dashboard.py"""
from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from app import db, tracker
from app.config import load_config

if os.getenv("JOB_AGENT_AUTHENTICATED") != "1":
    st.set_page_config(page_title="Job Agent", page_icon="🎯", layout="wide")
cfg = load_config()
TZ = ZoneInfo(cfg["timezone"])


@st.cache_resource
def get_conn():
    return db.connect()


conn = get_conn()

# ---- tabs that must work even before any jobs exist
def _checklist():
    import os
    from app.config import ROOT
    from app.resume import load_resume_text
    items = [
        ("Gmail connected", (ROOT / "token.json").exists() or bool(os.getenv("GMAIL_TOKEN_JSON"))),
        ("Gemini key set (.env)", bool(os.getenv("GEMINI_API_KEY"))),
        ("Resume added (Settings tab)", bool(load_resume_text())),
        ("Your name set (Settings tab)", (cfg["profile"].get("name") or "").strip() not in ("", "Your Name")),
    ]
    st.markdown("**Setup checklist**")
    for label, ok in items:
        st.write(("✅ " if ok else "⬜ ") + label)


def _summary():
    rows = conn.execute("SELECT sources, filter_status, COUNT(*) n FROM jobs GROUP BY sources, filter_status").fetchall()
    if not rows:
        return
    d = pd.DataFrame([dict(r) for r in rows])
    d["sources"] = d["sources"].fillna("?").str.replace(",", " + ")
    st.markdown("**What is in the database** (pending = collected but not checked yet)")
    st.dataframe(d.pivot_table(index="sources", columns="filter_status", values="n", aggfunc="sum", fill_value=0),
                 width="stretch")
    st.dataframe(pd.read_sql_query("SELECT link_status AS link_check, COUNT(*) AS jobs FROM jobs GROUP BY 1", getattr(conn, 'raw', conn)),
                 hide_index=True)
    all_df = pd.read_sql_query(
        "SELECT id,title,company,location,sources,posted_hint,posted_at,date_confidence,link_status,"
        "filter_status,filter_reason,match_score,match_verdict,url FROM jobs ORDER BY match_score DESC", getattr(conn, 'raw', conn))
    st.download_button("⬇ Download all jobs (CSV)", all_df.to_csv(index=False).encode("utf-8"),
                       "jobs.csv", "text/csv")


def _danger_zone():
    with st.expander("Danger zone"):
        sure = st.checkbox("I understand this deletes ALL collected jobs and tracker data")
        if st.button("🗑 Reset database", disabled=not sure):
            for t in ("status_history", "applications", "jobs", "processed_emails", "runs"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()
            st.rerun()


def _scan_controls():
    """Run the Gmail scan in a separate process so clicking around never interrupts it."""
    import os, subprocess, sys
    from app.config import ROOT
    log, pidf = ROOT / "data" / "run.log", ROOT / "data" / "run.pid"

    def running() -> bool:
        try:
            pid = int(pidf.read_text())
        except Exception:
            return False
        try:
            if os.name == "nt":
                out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
                return str(pid) in out
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    if running():
        st.info("⏳ Scan is running in the background. You can click around freely. Use Refresh to see progress.")
    elif st.button("📥 Scan my Gmail now", type="primary"):
        log.parent.mkdir(exist_ok=True)
        proc = subprocess.Popen([sys.executable, "-u", "-m", "app.run_daily"], cwd=ROOT,
                                stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT)
        pidf.write_text(str(proc.pid))
        st.rerun()
    c1, c2 = st.columns(2)
    if c1.button("🔄 Refresh"):
        st.rerun()
    if log.exists():
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-25:])
        st.caption("Latest scan log" + (" (still running)" if running() else " (finished)"))
        st.code(tail or "(empty)", language="text")

def render_pipeline():
    last = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if last:
        st.write(f"Last run: {last['finished_at']}")
        st.json(json.loads(last["stats"]))
    st.markdown("Run from a terminal: `python -m app.run_daily` (or `--demo` for sample data).")
    _checklist()
    st.divider()
    _scan_controls()
    st.divider()
    _summary()
    if st.button("▶ Run demo data now"):
        from app.demo import demo_messages
        from app.matcher import LocalMatcher
        from app.pipeline import run_pipeline
        c2 = load_config()
        c2["verification"]["fetch_pages"] = False
        with st.spinner("Running..."):
            run_pipeline(conn, c2, messages_by_source=demo_messages(), matcher=LocalMatcher(c2),
                         notify_email=False, sleep=False)
        st.rerun()
    _danger_zone()



def _lines(text: str) -> list[str]:
    seen, out = set(), []
    for ln in text.replace(",", "\n").splitlines():
        v = ln.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def render_settings():
    from app.config import ROOT, save_user_config

    st.subheader("Roles, cities and filters")
    st.caption("One item per line (commas also work). Saved to config.yaml. "
               "After saving, use “Re-apply settings to existing jobs” to re-check jobs already collected.")
    p_, f_, m_ = cfg["profile"], cfg["filters"], cfg["matching"]
    with st.form("settings"):
        a, b = st.columns(2)
        name = a.text_input("Your name", p_.get("name", ""))
        grad = b.number_input("Graduation year", 2000, 2040, int(p_.get("graduation_year") or 2026))
        roles = a.text_area("Target roles (job must match at least one)", "\n".join(p_["target_roles"]), height=260)
        skills = b.text_area("Your skills (added to what is found in your resume)", "\n".join(p_["skills"]), height=120)
        avoid = b.text_area("Skip if the TITLE contains", "\n".join(p_["avoid_title_keywords"]), height=120)
        cities = a.text_area("Locations (add any city; include Remote if you want remote jobs)",
                             "\n".join(cfg["locations"]), height=200)
        levels = b.text_area("Entry-level words", "\n".join(p_["levels"]), height=120)
        c1, c2, c3 = st.columns(3)
        max_exp = c1.number_input("Max years of experience required", 0, 10, int(p_["max_experience_years"]))
        max_age = c2.number_input("Max job age (hours)", 1, 168, int(f_["max_age_hours"]))
        c3.caption("Every job that passes your rules is emailed. There is no score cut-off.")
        d1, d2 = st.columns(2)
        policies = ["allow_hints", "verified_only", "allow_unverified"]
        policy = d1.selectbox("Date trust", policies, index=policies.index(f_["date_policy"]),
                              help="verified_only = page date only. allow_hints = also the '2 hours ago' text in the email. "
                                   "allow_unverified = also the email date (least strict).")
        unk = d2.selectbox("Unknown location", ["keep", "reject"], index=["keep", "reject"].index(f_["unknown_location"]))
        req_lvl = st.checkbox("Only entry-level jobs (must mention intern / fresher / 0-1 yrs)", p_["require_level_signal"])
        notes = st.text_area("Notes for the AI matcher (e.g. “prefer data roles, interested in ML”)", p_.get("notes", ""))
        saved = st.form_submit_button("💾 Save settings", type="primary")
    if saved:
        save_user_config({
            "profile": {"name": name, "graduation_year": int(grad), "target_roles": _lines(roles),
                        "skills": _lines(skills), "avoid_title_keywords": _lines(avoid), "levels": _lines(levels),
                        "max_experience_years": int(max_exp), "require_level_signal": req_lvl, "notes": notes},
            "locations": _lines(cities),
            "filters": {"max_age_hours": int(max_age), "date_policy": policy, "unknown_location": unk},
        })
        st.success("Saved to config.yaml")
        st.rerun()

    if st.button("🔁 Re-apply settings to existing jobs"):
        from app.pipeline import reevaluate
        with st.spinner("Re-checking jobs..."):
            res = reevaluate(conn, load_config())
        st.success(f"Done: {res['filter']['accepted']} matching, {res['filter']['rejected']} rejected.")
        st.rerun()

    st.divider()
    st.subheader("Connect Gmail")
    cred, tok = ROOT / "credentials.json", ROOT / "token.json"
    st.write(("✅ Gmail connected (token.json found)" if tok.exists() else "❌ Gmail not connected yet"))
    if not cred.exists():
        st.info("Step 1: upload the OAuth **Desktop app** `credentials.json` from Google Cloud Console "
                "(see README section 3).")
        up = st.file_uploader("credentials.json", type="json", key="cred_up")
        if up is not None:
            cred.write_bytes(up.getvalue())
            st.success("Saved credentials.json")
            st.rerun()
    else:
        st.write("✅ credentials.json found")
        if st.button("🔐 Sign in to Gmail (opens a browser window)"):
            from app.gmail_client import get_service, own_address, run_oauth_flow
            try:
                with st.spinner("Complete the Google sign-in in the browser window..."):
                    run_oauth_flow()
                    addr = own_address(get_service())
                st.success(f"Connected as {addr}")
            except Exception as e:
                st.error(f"Could not connect: {e}")

    st.divider()
    st.subheader("Resume")
    (ROOT / "resume").mkdir(exist_ok=True)
    have = [f.name for f in (ROOT / "resume").glob("*") if f.suffix.lower() in (".pdf", ".docx", ".txt", ".md")]
    st.write("Current resume file(s): " + (", ".join(have) if have else "none"))
    rup = st.file_uploader("Upload resume (PDF, DOCX or TXT)", type=["pdf", "docx", "txt"], key="resume_up")
    if rup is not None:
        (ROOT / "resume" / rup.name).write_bytes(rup.getvalue())
        st.success(f"Saved resume/{rup.name}")

    st.divider()
    st.subheader("Gemini key")
    import os
    st.write("✅ GEMINI_API_KEY is set" if os.getenv("GEMINI_API_KEY") else "❌ Not set")
    st.caption("Optional: the job emails do NOT need this key. It is only used if you enable AI scoring "
               "(`matching.enabled: true`), and then only for sorting.")
    with st.form("gemini_key"):
        key = st.text_input("Gemini API key", type="password", placeholder="paste key from aistudio.google.com/apikey")
        if st.form_submit_button("💾 Save key"):
            if key.strip():
                from app.config import save_env_var
                save_env_var("GEMINI_API_KEY", key.strip())
                st.success("Saved to .env and active now.")
                st.rerun()
            else:
                st.warning("Paste a key first.")



def load_jobs() -> pd.DataFrame:
    df = pd.read_sql_query(
        """SELECT j.*, a.status AS app_status, a.applied_date, a.notes AS app_notes
           FROM jobs j LEFT JOIN applications a ON a.job_id=j.id""", getattr(conn, 'raw', conn))
    if df.empty:
        return df
    for c in ("first_seen", "posted_at"):
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce").dt.tz_convert(TZ)
    df["age_h"] = ((pd.Timestamp.now(tz=TZ) - df["posted_at"]).dt.total_seconds() / 3600).round(0)
    df["status"] = df["app_status"].fillna("-")
    return df


df = load_jobs()
st.title("🎯 Job Agent")
st.caption("Nothing is ever applied for automatically — you review, apply yourself, then track it here.")

if df.empty:
    st.info("No jobs yet. Connect Gmail in **Settings**, then click **Scan my Gmail now** in Pipeline "
            "(or click **Run demo data now** to see sample jobs).")
    t_run, t_set = st.tabs(["▶️ Pipeline", "⚙️ Settings"])
    with t_run:
        render_pipeline()
    with t_set:
        render_settings()
    st.stop()

# ------------------------------------------------------------ sidebar filters
with st.sidebar:
    st.header("Filters")
    view = st.radio("Show", ["Matching (accepted)", "Rejected", "All"], index=0)
    sources = sorted({s for v in df["sources"].dropna() for s in v.split(",")})
    pick_src = st.multiselect("Source", sources, default=sources)
    cities = sorted(c for c in df["canonical_location"].dropna().unique() if c)
    pick_city = st.multiselect("Location", cities, default=cities)
    min_score = st.slider("Min match score", 0, 100, 0)
    role_q = st.text_input("Role / company contains")
    only_today = st.checkbox("First seen today only", value=False)
    pick_status = st.multiselect("Tracker status", ["-"] + tracker.STATUSES)

f = df.copy()
if view.startswith("Matching"):
    f = f[f["filter_status"] == "accepted"]
elif view == "Rejected":
    f = f[f["filter_status"] == "rejected"]
f = f[pd.Series([any(x in pick_src for x in str(s).split(",")) for s in f["sources"].fillna("")],
               index=f.index, dtype=bool)]
if view != "Rejected":
    f = f[f["canonical_location"].isin(pick_city) | f["canonical_location"].isna() | (f["canonical_location"] == "")]
    f = f[f["match_score"].fillna(0) >= min_score]
if role_q:
    q = role_q.lower()
    f = f[f["title"].str.lower().str.contains(q) | f["company"].fillna("").str.lower().str.contains(q)]
if only_today:
    f = f[f["first_seen"].dt.date == dt.datetime.now(TZ).date()]
if pick_status:
    f = f[f["status"].isin(pick_status)]
f = f.sort_values(["match_score", "first_seen"], ascending=[False, False], na_position="last")

tab_over, tab_jobs, tab_track, tab_run, tab_set = st.tabs(
    ["📊 Overview", "💼 Jobs", "🗂 Tracker", "▶️ Pipeline", "⚙️ Settings"])

# ------------------------------------------------------------------ overview
with tab_over:
    today = dt.datetime.now(TZ).date()
    acc = df[df["filter_status"] == "accepted"]
    c = st.columns(5)
    c[0].metric("Seen today", int((df["first_seen"].dt.date == today).sum()))
    c[1].metric("Matching", len(acc))
    c[2].metric("In tracker", int(df["status"].notna().sum()))
    c[3].metric("Applied", int((df["status"] == "Applied").sum()))
    c[4].metric("Interviews / offers", int(df["status"].isin(["Interview scheduled", "Offer received"]).sum()))
    pend = int((df["filter_status"] == "pending").sum())
    if pend:
        st.warning(f"{pend} collected jobs have not been checked yet. Open the Pipeline tab and click "
                   "“Scan my Gmail now” to finish checking them.")
    l, r = st.columns(2)
    src = pd.Series([s for v in acc["sources"].dropna() for s in v.split(",")]).value_counts()
    l.subheader("Matching jobs by source")
    if not src.empty:
        l.bar_chart(src)
    else:
        l.caption("No matching jobs yet.")
    r.subheader("Matching jobs by city")
    byc = acc["canonical_location"].replace("", pd.NA).dropna().value_counts()
    if not byc.empty:
        r.bar_chart(byc)
    else:
        r.caption("No matching jobs yet.")
    st.subheader("Why jobs were rejected")
    rej = df[df["filter_status"] == "rejected"]["filter_reason"].str.replace(r"\d+", "N", regex=True)
    if not rej.empty:
        st.dataframe(rej.value_counts().rename("jobs"), width="stretch")
    else:
        st.caption("No rejected jobs yet.")

# ---------------------------------------------------------------------- jobs
with tab_jobs:
    st.write(f"**{len(f)}** jobs")
    if f.empty:
        n_pend = int((df["filter_status"] == "pending").sum())
        st.info(f"{n_pend} jobs are collected but still waiting to be checked. Finish the scan in the Pipeline tab."
                if n_pend else "Nothing matches the current filters. Try the “Rejected” or “All” view in the sidebar.")
    show = f[["match_score", "title", "company", "canonical_location", "sources", "age_h",
              "date_confidence", "link_status", "status"]].rename(columns={
        "match_score": "score", "canonical_location": "city", "age_h": "age (h)",
        "date_confidence": "date from", "link_status": "link"})
    ev = st.dataframe(show, width="stretch", hide_index=True, on_select="rerun",
                      selection_mode="single-row", height=330)
    rows = ev.selection.rows if ev and ev.selection else []
    if rows:
        j = f.iloc[rows[0]]
        jid = int(j["id"])
        st.divider()
        st.subheader(f"{j['title']} — {j['company']}")
        st.write(f"📍 {j['location'] or 'n/a'}  |  🔎 {j['sources']}  |  "
                 f"🕒 posted ~{j['age_h']:.0f}h ago ({j['date_confidence']})  |  🔗 link: {j['link_status']}")
        if pd.notna(j["match_score"]):
            st.progress(int(j["match_score"]) / 100, text=f"{int(j['match_score'])}% — {j['match_verdict']} "
                                                          f"({j['match_provider']})")
            a, b = st.columns(2)
            a.markdown("**Why it matches**\n" + "\n".join(f"- {x}" for x in json.loads(j["match_reasons"] or "[]")))
            b.markdown("**Gaps / risks**\n" + "\n".join(f"- {x}" for x in json.loads(j["match_gaps"] or "[]")))
        else:
            st.caption(f"Filter result: {j['filter_status']} — {j['filter_reason']}")
        st.markdown("**Apply links** (open and apply yourself)")
        for u in json.loads(j["urls_json"] or "[]"):
            st.markdown(f"- [{u['source']}]({u['url']})")
        with st.expander("Description"):
            st.write(j["description"] or "—")
        cur = tracker.get(conn, jid)
        with st.form(f"track_{jid}"):
            st.markdown("**Application tracker**")
            opts = tracker.STATUSES
            status = st.selectbox("Status", opts, index=opts.index(cur["status"]) if cur else 1)
            applied = st.date_input("Applied on", value=dt.date.fromisoformat(cur["applied_date"])
                                    if cur and cur["applied_date"] else None)
            link = st.text_input("Link", value=(cur["link"] if cur else j["url"]) or "")
            notes = st.text_area("Notes", value=cur["notes"] if cur else "")
            if st.form_submit_button("Save"):
                tracker.set_status(conn, jid, status, applied.isoformat() if applied else None, link, notes)
                st.success("Saved")
                st.rerun()
        hist = tracker.history(conn, jid)
        if hist:
            st.caption("History: " + " → ".join(f"{h['status']} ({h['changed_at'][:10]})" for h in hist))

# ------------------------------------------------------------------- tracker
with tab_track:
    cnt = tracker.counts(conn)
    cols = st.columns(len(cnt))
    for col, (s, n) in zip(cols, cnt.items()):
        col.metric(s, n)
    tracked = tracker.list_tracked(conn)
    if not tracked:
        st.info("Nothing tracked yet. Shortlisted jobs appear here automatically.")
    else:
        t = pd.DataFrame([dict(r) for r in tracked])
        edit = t[["job_id", "title", "company", "match_score", "status", "applied_date", "notes", "job_url"]]
        out = st.data_editor(
            edit, hide_index=True, width="stretch", key="tracker_editor",
            disabled=["job_id", "title", "company", "match_score", "job_url"],
            column_config={"status": st.column_config.SelectboxColumn(options=tracker.STATUSES, required=True),
                           "job_url": st.column_config.LinkColumn("link")})
        if st.button("Save tracker changes"):
            n = 0
            for old, new in zip(edit.to_dict("records"), out.to_dict("records")):
                if (old["status"], old["applied_date"], old["notes"]) != (new["status"], new["applied_date"], new["notes"]):
                    tracker.set_status(conn, int(new["job_id"]), new["status"],
                                       new["applied_date"] or None, None, new["notes"] or "")
                    n += 1
            st.success(f"Updated {n} row(s)")
            st.rerun()


with tab_run:
    render_pipeline()
with tab_set:
    render_settings()
