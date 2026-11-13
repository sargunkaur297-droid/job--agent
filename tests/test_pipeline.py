import datetime as dt
import json

from app import db, notify, tracker
from app.matcher import LocalMatcher
from app.models import FetchResult
from app.pipeline import run_pipeline

from conftest import NOW


def run(conn, cfg, messages, **kw):
    kw.setdefault("matcher", LocalMatcher(cfg))
    kw.setdefault("resume_text", "Python SQL pandas Power BI Excel machine learning")
    return run_pipeline(conn, cfg, messages_by_source=messages, notify_email=False, now=NOW, sleep=False, **kw)


def rows(conn, where="1=1"):
    return conn.execute(f"SELECT * FROM jobs WHERE {where}").fetchall()


def test_full_workflow_counts(conn, cfg, messages):
    stats = run(conn, cfg, messages)
    assert stats["ingest"]["jobs_parsed"] == 10
    assert len(rows(conn)) == 9                      # Acme duplicate merged across indeed+linkedin
    acc = {r["title"] for r in rows(conn, "filter_status='accepted'")}
    assert "Data Analyst Intern" in acc and "Machine Learning Engineer" in acc
    reasons = {r["title"]: r["filter_reason"] for r in rows(conn, "filter_status='rejected'")}
    assert "senior" in reasons["Senior Data Engineer"]
    assert "not in your target" in reasons["Python Developer Trainee"]
    assert "120h" in reasons["Software Engineer - Fresher"]
    assert "3+ years" in reasons["QA Engineer"]


def test_duplicates_across_platforms_merge(conn, cfg, messages):
    run(conn, cfg, messages)
    r = rows(conn, "title='Data Analyst Intern'")[0]
    assert set(r["sources"].split(",")) == {"indeed", "linkedin"}
    assert len(json.loads(r["urls_json"])) == 2


def test_rerun_is_idempotent(conn, cfg, messages):
    run(conn, cfg, messages)
    n = len(rows(conn))
    stats = run(conn, cfg, messages)                 # same emails again
    assert stats["ingest"]["emails"] == 0 and len(rows(conn)) == n


def test_ranking_scores_and_reasons(conn, cfg, messages):
    cfg["matching"]["enabled"] = True                # AI/local score is optional (sorting only)
    run(conn, cfg, messages)
    best = rows(conn, "match_score IS NOT NULL ORDER BY match_score DESC")
    assert best[0]["match_score"] >= best[-1]["match_score"]
    assert json.loads(best[0]["match_reasons"])
    assert all(0 <= r["match_score"] <= 100 for r in best)


def test_shortlist_creates_tracker_rows(conn, cfg, messages):
    run(conn, cfg, messages)
    assert tracker.counts(conn)["Shortlisted"] >= 1


def test_page_verification_updates_date_and_expiry(conn, cfg, messages):
    cfg["verification"]["fetch_pages"] = True

    def fetcher(url):
        if "3912399999" in url:                      # LinkedIn Zeta -> expired page
            return FetchResult(url, 200, "<html>This job is no longer available</html>")
        if "3912300001" in url:                      # Cloudly -> 404
            return FetchResult(url, 404, "")
        if "110100654321" in url:                    # DataWave -> blocked, stays unverifiable
            return FetchResult(url, 403, "")
        if "aaa111" in url:                          # Acme -> page says posted 30h ago -> too old
            return FetchResult(url, 200, '<script type="application/ld+json">{"@type":"JobPosting",'
                               '"datePosted":"2026-11-12T00:00:00+00:00"}</script>')
        return FetchResult(url, 200, "<html>ok</html>")

    stats = run(conn, cfg, messages, fetcher=fetcher)
    assert stats["verify"]["expired"] >= 1 and stats["verify"]["broken"] >= 1
    by = {r["title"]: r for r in rows(conn)}
    assert by["Associate Software Engineer"]["filter_status"] == "rejected"
    assert by["Backend Developer (Remote)"]["link_status"] == "broken"
    assert by["Machine Learning Engineer"]["filter_status"] == "accepted"
    assert by["Machine Learning Engineer"]["link_status"] == "unverifiable"
    assert by["Data Analyst Intern"]["date_confidence"] == "page"
    assert by["Data Analyst Intern"]["filter_status"] == "rejected"


# ------------------------------------------------------------------ tracker
def test_tracker_workflow(conn, cfg, messages):
    run(conn, cfg, messages)
    jid = rows(conn, "title='Data Analyst Intern'")[0]["id"]
    tracker.set_status(conn, jid, "Applied", notes="via portal")
    a = tracker.get(conn, jid)
    assert a["status"] == "Applied" and a["applied_date"] and a["notes"] == "via portal" and a["link"]
    tracker.set_status(conn, jid, "Interview scheduled")
    assert tracker.get(conn, jid)["applied_date"] == a["applied_date"]   # preserved
    assert [h["status"] for h in tracker.history(conn, jid)][-2:] == ["Applied", "Interview scheduled"]
    tracker.set_status(conn, jid, "Offer received")
    assert tracker.counts(conn)["Offer received"] == 1


def test_tracker_rejects_bad_status(conn, cfg, messages):
    run(conn, cfg, messages)
    try:
        tracker.set_status(conn, 1, "Hired!!")
        assert False
    except ValueError:
        pass


# ----------------------------------------------------------- notifications
def test_digest_sent_once(conn, cfg, messages):
    run(conn, cfg, messages)
    sent = []
    sender = lambda to, subj, body: sent.append((subj, body))
    cfg["notifications"]["mode"] = "new_only"
    cfg["notifications"]["send_empty_digest"] = False
    r1 = notify.send_digest(conn, cfg, sender, NOW)
    assert r1["sent"] >= 1 and "Nothing is applied for automatically" in sent[0][1]
    r2 = notify.send_digest(conn, cfg, sender, NOW)  # nothing new -> no second email
    assert r2["sent"] == 0 and len(sent) == 1


def test_digest_includes_only_new_jobs_later(conn, cfg, messages):
    cfg["notifications"]["mode"] = "new_only"
    run(conn, cfg, messages)
    notify.send_digest(conn, cfg, lambda *a: None, NOW)
    extra = {"linkedin": [type(messages["linkedin"][0])(
        "m-new", "x", "x", NOW, html=messages["linkedin"][0].html.replace("3912300001", "3912300002")
        .replace("Backend Developer (Remote)", "Python Developer Intern").replace("Cloudly", "NewCo"))]}
    run(conn, cfg, extra)
    sent = []
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    assert sent and "Python Developer Intern" in sent[0] and "Data Analyst Intern" not in sent[0]


# ------------------------------------------------- early rejection / recovery
def test_obvious_rejects_never_fetch_pages(conn, cfg, messages):
    """City / role / seniority rejects must be decided BEFORE opening job pages (saves minutes)."""
    cfg["verification"]["fetch_pages"] = True
    fetched = []

    def fetcher(url):
        fetched.append(url)
        return FetchResult(url, 200, "<html>ok</html>")

    run(conn, cfg, messages, fetcher=fetcher)
    joined = " ".join(fetched)
    assert "ddd444eee555fff6" not in joined      # Senior Data Engineer
    assert "ggg777hhh888iii9" not in joined      # Kolkata job
    assert "110100777777" not in joined          # QA Engineer needing 3+ years
    assert "aaa111bbb222ccc3" in joined          # a good job IS checked


def test_stuck_pending_jobs_are_recovered_on_next_run(conn, cfg, messages):
    """Simulate an interrupted scan: jobs ingested but never filtered. Next run must finish them."""
    from app.pipeline import ingest
    ingest(conn, cfg, messages, NOW)
    assert rows(conn, "filter_status='pending'")           # the stuck state
    stats = run(conn, cfg, {})                              # no new emails
    assert not rows(conn, "filter_status='pending'")
    assert stats["filter"]["accepted"] >= 1
    assert rows(conn, "filter_status='accepted'")


# ------------------------------------------- all jobs, no score cut-off, big emails
def test_every_accepted_job_is_emailed_regardless_of_score(conn, cfg, messages):
    cfg["matching"]["enabled"] = True
    run(conn, cfg, messages)
    conn.execute("UPDATE jobs SET match_score=1 WHERE filter_status='accepted'")   # absurdly low scores
    conn.commit()
    sent = []
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    accepted = rows(conn, "filter_status='accepted'")
    assert accepted and sum(b.count("<tr><td") for b in sent) == len(accepted)
    assert tracker.counts(conn)["Shortlisted"] == len(accepted)


def test_email_has_role_link_and_location(conn, cfg, messages):
    run(conn, cfg, messages)
    sent = []
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    j = rows(conn, "title='Data Analyst Intern'")[0]
    assert j["url"] in sent[0] and "Data Analyst Intern" in sent[0] and (j["location"] or "Bengaluru") in sent[0]


def _bulk(conn, n, now=NOW):
    ts = db.iso(now)
    for i in range(n):
        conn.execute(
            "INSERT INTO jobs(fingerprint,title,company,location,url,urls_json,sources,posted_at,date_confidence,"
            "link_status,filter_status,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"fp{i}", f"Data Analyst {i}", f"Company {i}", "Bengaluru", f"https://www.linkedin.com/jobs/view/{3900000000 + i}",
             json.dumps([{"source": "linkedin", "url": f"https://www.linkedin.com/jobs/view/{3900000000 + i}"}]),
             "linkedin", ts, "hint", "ok", "accepted", ts, ts))
    conn.commit()


def test_one_email_holds_120_jobs(conn, cfg):
    _bulk(conn, 120)
    sent = []
    r = notify.send_digest(conn, cfg, lambda to, s, b: sent.append((s, b)), NOW)
    assert r["sent"] == 120 and r["emails"] == 1 and sent[0][1].count("<tr><td") == 120
    assert len(sent[0][1].encode()) < notify.GMAIL_SAFE_BYTES


def test_huge_lists_split_into_several_emails(conn, cfg):
    _bulk(conn, 400)
    sent = []
    r = notify.send_digest(conn, cfg, lambda to, s, b: sent.append((s, b)), NOW)
    assert r["sent"] == 400 and r["emails"] == len(sent) >= 3
    assert all(len(b.encode()) < notify.GMAIL_SAFE_BYTES for _, b in sent)
    assert sum(b.count("<tr><td") for _, b in sent) == 400


def test_old_jobs_excluded_and_empty_email_still_sent(conn, cfg):
    _bulk(conn, 3, now=NOW - dt.timedelta(hours=30))          # older than 24h
    sent = []
    r = notify.send_digest(conn, cfg, lambda to, s, b: sent.append((s, b)), NOW)
    assert r["sent"] == 0 and len(sent) == 1 and "0 jobs" in sent[0][0]


def test_last_24h_mode_resends_everything_each_run(conn, cfg):
    _bulk(conn, 5)
    sent = []
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    assert [b.count("<tr><td") for b in sent] == [5, 5]


# ------------------------------------------------ suggestions 1-5
def _pending_job(conn, urls, title="Data Analyst"):
    ts = db.iso(NOW)
    conn.execute(
        "INSERT INTO jobs(fingerprint,title,company,location,url,urls_json,sources,posted_at,date_confidence,"
        "filter_status,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, title, "Co", "Bengaluru", urls[0], json.dumps([{"source": "x", "url": u} for u in urls]),
         "x", ts, "hint", "pending", ts, ts))
    conn.commit()


def test_blocked_page_is_retried_once_and_recovers(conn, cfg):
    from app import verify
    cfg["verification"]["fetch_pages"] = True
    _pending_job(conn, ["https://example.com/job/1"])
    calls = []

    def fetcher(u):
        calls.append(u)
        return FetchResult(u, 403 if len(calls) == 1 else 200, "" if len(calls) == 1 else "<html>ok</html>")

    stats = verify.verify_pending(conn, cfg, fetcher, NOW, sleep=False)
    assert len(calls) == 2 and stats["ok"] == 1
    assert rows(conn)[0]["link_status"] == "ok"


def test_url_that_opens_becomes_the_primary_link(conn, cfg):
    from app import verify
    cfg["verification"]["fetch_pages"] = True
    _pending_job(conn, ["https://www.indeed.com/viewjob?jk=dead", "https://www.naukri.com/job-listings-good-1"])
    fetch = lambda u: FetchResult(u, 404, "") if "dead" in u else FetchResult(u, 200, "<html>ok</html>")
    verify.verify_pending(conn, cfg, fetch, NOW, sleep=False)
    r = rows(conn)[0]
    assert r["link_status"] == "ok" and r["url"].endswith("job-listings-good-1")


def test_linkedin_guest_page_used_when_main_page_blocked(conn, cfg):
    from app import verify
    cfg["verification"]["fetch_pages"] = True
    _pending_job(conn, ["https://www.linkedin.com/jobs/view/3912300777"])
    fetch = lambda u: FetchResult(u, 200, "<html>ok</html>") if "jobs-guest" in u else FetchResult(u, 429, "")
    verify.verify_pending(conn, cfg, fetch, NOW, sleep=False)
    assert rows(conn)[0]["link_status"] == "ok"


def test_source_warnings_in_email(conn, cfg, messages):
    run(conn, cfg, {"indeed": messages["indeed"]})            # linkedin + naukri sent nothing
    sent = []
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    assert "LinkedIn: no alert emails" in sent[0] and "Naukri: no alert emails" in sent[0]
    assert "Indeed: no alert" not in sent[0]
    # layout change: emails read but nothing parsed
    conn.execute("UPDATE processed_emails SET jobs_found=0 WHERE source='indeed'")
    conn.commit()
    sent.clear()
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    assert "Indeed: " in sent[0] and "layout may have changed" in sent[0]


def test_filtered_out_section_lists_reasons(conn, cfg, messages):
    run(conn, cfg, messages)
    sent = []
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    body = sent[-1]
    assert "Filtered out by your rules" in body and "Senior Data Engineer" in body and "seniority" in body
    cfg["notifications"]["show_filtered_out"] = False
    sent.clear()
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    assert "Filtered out by your rules" not in sent[-1]


def test_filtered_out_list_shrinks_to_fit_gmail(conn, cfg):
    _bulk(conn, 140)                                          # nearly fills one email
    ts = db.iso(NOW)
    for i in range(300):
        conn.execute("INSERT INTO jobs(fingerprint,title,company,location,url,sources,filter_status,filter_reason,"
                     "first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (f"rej{i}", f"Some Other Role {i}", "X", "Kolkata", f"https://e.com/{i}", "indeed",
                      "rejected", f"location 'Kolkata {i}' is not in your target cities", ts, ts))
    conn.commit()
    sent = []
    notify.send_digest(conn, cfg, lambda t, s, b: sent.append(b), NOW)
    assert all(len(b.encode()) < notify.GMAIL_SAFE_BYTES for b in sent)
    assert sum(b.count("<tr><td") for b in sent) == 140


def test_expired_gmail_login_exits_with_code_2(monkeypatch):
    from app import gmail_client, run_daily

    def boom():
        raise gmail_client.GmailAuthError("expired")

    monkeypatch.setattr(gmail_client, "get_service", boom)
    assert run_daily.main([]) == 2
