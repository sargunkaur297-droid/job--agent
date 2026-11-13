"""End-to-end pipeline: ingest -> dedupe -> verify -> filter -> match -> shortlist -> notify."""
from __future__ import annotations

import datetime as dt
import json
import os
import time

from . import db, filters, notify, tracker, verify
from .dates import parse_hint
from .locations import detect_cities
from .matcher import make_matcher
from .models import EmailMessage, ParsedJob
from .normalize import fingerprint, norm_company, norm_text, norm_title
from .parsers import parse_email
from .resume import load_resume_text


def to_record(pj: ParsedJob, email_date: dt.datetime, cfg: dict) -> dict:
    cities = [c for c in detect_cities(pj.location, cfg["locations"]) if c in cfg["locations"]]
    city = cities[0] if cities else ""
    comp, title = norm_company(pj.company), norm_title(pj.title)
    hint_dt = parse_hint(pj.posted_hint, email_date)
    return {
        "source": pj.source, "title": pj.title, "company": pj.company, "location": pj.location,
        "description": pj.description, "url": pj.url, "posted_hint": pj.posted_hint,
        "company_norm": comp, "title_norm": title, "city_norm": norm_text(city),
        "fingerprint": fingerprint(comp, title, norm_text(city)),
        "email_date": db.iso(email_date),
        "posted_at": db.iso(hint_dt or email_date),
        "date_confidence": "hint" if hint_dt else "email",
    }


def ingest(conn, cfg: dict, messages_by_source: dict[str, list[EmailMessage]], now=None) -> dict:
    stats = {"emails": 0, "jobs_parsed": 0, "new_jobs": 0, "duplicates": 0}
    for source, messages in messages_by_source.items():
        for m in messages:
            if conn.execute("SELECT 1 FROM processed_emails WHERE message_id=?", (m.id,)).fetchone():
                continue
            try:
                parsed = parse_email(source, m.html)
            except Exception as e:
                print(f"[ingest] could not parse {source} email {m.id}: {e}")
                parsed = []
            for pj in parsed:
                _, is_new = db.upsert_job(conn, to_record(pj, m.date, cfg), now)
                stats["new_jobs" if is_new else "duplicates"] += 1
            stats["emails"] += 1
            stats["jobs_parsed"] += len(parsed)
            conn.execute("INSERT INTO processed_emails VALUES(?,?,?,?)",
                         (m.id, source, db.iso(now or db.now_utc()), len(parsed)))
            conn.commit()
    return stats


def _city(row, cfg):
    cities = detect_cities(row["location"] or "", cfg["locations"])
    return next((c for c in cities if c in cfg["locations"]), "")


def prefilter(conn, cfg: dict, now=None) -> dict:
    """Reject obviously unsuitable jobs (city, role, seniority, experience) BEFORE opening job pages."""
    now = now or db.now_utc()
    n = 0
    for r in conn.execute("SELECT * FROM jobs WHERE filter_status='pending'").fetchall():
        status, reason = filters.evaluate(dict(r), cfg, now, cheap_only=True)
        if status == "rejected":
            conn.execute("UPDATE jobs SET filter_status='rejected', filter_reason=?, canonical_location=? WHERE id=?",
                         (reason, _city(r, cfg), r["id"]))
            n += 1
    conn.commit()
    return {"rejected_early": n}


def filter_pending(conn, cfg: dict, now=None) -> dict:
    now = now or db.now_utc()
    stats = {"accepted": 0, "rejected": 0}
    for r in conn.execute("SELECT * FROM jobs WHERE filter_status='pending'").fetchall():
        status, reason = filters.evaluate(dict(r), cfg, now)
        city = detect_cities(r["location"] or "", cfg["locations"])
        city = next((c for c in city if c in cfg["locations"]), "")
        conn.execute("UPDATE jobs SET filter_status=?, filter_reason=?, canonical_location=? WHERE id=?",
                     (status, reason, city, r["id"]))
        stats[status] += 1
    conn.commit()
    return stats


def match_accepted(conn, cfg: dict, matcher, resume_text: str, sleep: bool = True) -> dict:
    """Every accepted job goes to the tracker/email. The score (optional) is only for sorting in the dashboard."""
    m = cfg["matching"]
    if not m.get("enabled", False):
        ids = [r[0] for r in conn.execute("SELECT id FROM jobs WHERE filter_status='accepted'")]
        for jid in ids:
            tracker.ensure_shortlisted(conn, jid)
        return {"matched": 0, "shortlisted": len(ids), "scoring": "off"}
    rows = conn.execute(
        "SELECT * FROM jobs WHERE filter_status='accepted' AND match_score IS NULL "
        "ORDER BY first_seen DESC LIMIT ?", (m.get("max_jobs_per_run", 60),)).fetchall()
    stats = {"matched": 0, "shortlisted": 0}
    for r in rows:
        res = matcher.score(dict(r), resume_text)
        print(f"      scored {stats['matched'] + 1}/{len(rows)}: {res.score}% {r['title'][:50]}", flush=True)
        conn.execute(
            "UPDATE jobs SET match_score=?, match_verdict=?, match_reasons=?, match_gaps=?, match_provider=? "
            "WHERE id=?", (res.score, res.verdict, json.dumps(res.reasons), json.dumps(res.gaps),
                           res.provider, r["id"]))
        conn.commit()
        stats["matched"] += 1
        tracker.ensure_shortlisted(conn, r["id"])      # never dropped because of a low score
        stats["shortlisted"] += 1
        if sleep and getattr(matcher, "name", "") == "gemini":
            time.sleep(m.get("delay_seconds", 4.0))
    return stats


def collect_messages(service, conn, cfg: dict) -> dict[str, list[EmailMessage]]:
    from .gmail_client import fetch_messages
    g = cfg["gmail"]
    seen = {r[0] for r in conn.execute("SELECT message_id FROM processed_emails")}
    return {src: fetch_messages(service, q.format(days=g["lookback_days"]),
                                g["max_emails_per_source"], seen)
            for src, q in g["queries"].items()}


def run_pipeline(conn, cfg: dict, *, messages_by_source=None, service=None, fetcher=None,
                 matcher=None, resume_text: str | None = None, notify_email: bool = True,
                 now: dt.datetime | None = None, sleep: bool = True) -> dict:
    started = now or db.now_utc()
    stats: dict = {}
    if messages_by_source is None and service is not None:
        messages_by_source = collect_messages(service, conn, cfg)
    print("[1/5] reading emails...", flush=True)
    stats["ingest"] = ingest(conn, cfg, messages_by_source or {}, started)
    print(f"      {stats['ingest']}", flush=True)
    stats["prefilter"] = prefilter(conn, cfg, started)
    todo = conn.execute("SELECT COUNT(*) FROM jobs WHERE filter_status='pending' AND link_status='unchecked'").fetchone()[0]
    print(f"[2/5] checking {todo} job pages (others were rejected early: {stats['prefilter']['rejected_early']})...", flush=True)
    stats["verify"] = verify.verify_pending(conn, cfg, fetcher, started, sleep)
    print("[3/5] applying filters...", flush=True)
    stats["filter"] = filter_pending(conn, cfg, started)
    print(f"      {stats['filter']}", flush=True)
    print("[4/5] adding matching jobs to the tracker (AI score is optional)...", flush=True)
    if cfg["matching"].get("enabled", False):
        resume_text = load_resume_text() if resume_text is None else resume_text
        matcher = matcher or make_matcher(cfg, os.getenv("GEMINI_API_KEY"))
    stats["match"] = match_accepted(conn, cfg, matcher, resume_text or "", sleep)
    sender = None
    if notify_email and service is not None and cfg["notifications"].get("send_email"):
        from .gmail_client import send_email
        sender = lambda to, subj, body: send_email(service, to, subj, body)
    print("[5/5] notifications...", flush=True)
    stats["notify"] = notify.send_digest(conn, cfg, sender, started, stats)
    print("Done.", flush=True)
    conn.execute("INSERT INTO runs(started_at, finished_at, stats) VALUES(?,?,?)",
                 (db.iso(started), db.iso(db.now_utc()), json.dumps(stats)))
    conn.commit()
    return stats


def reevaluate(conn, cfg: dict, matcher=None, resume_text: str | None = None, now=None) -> dict:
    """Re-run filters + matching on existing jobs after you change roles/cities/etc.
    Jobs you are tracking (applied, interview...) are left alone."""
    conn.execute("""UPDATE jobs SET filter_status='pending', filter_reason='', match_score=NULL
                    WHERE id NOT IN (SELECT job_id FROM applications WHERE status NOT IN ('Shortlisted'))""")
    conn.commit()
    out = {"filter": filter_pending(conn, cfg, now)}
    if cfg["matching"].get("enabled", False):
        resume_text = load_resume_text() if resume_text is None else resume_text
        matcher = matcher or make_matcher(cfg, os.getenv("GEMINI_API_KEY"))
    out["match"] = match_accepted(conn, cfg, matcher, resume_text or "", sleep=False)
    return out
