"""SQLite storage."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT UNIQUE,
  company_norm TEXT, title_norm TEXT, city_norm TEXT,
  title TEXT, company TEXT, location TEXT, canonical_location TEXT, description TEXT,
  url TEXT, urls_json TEXT DEFAULT '[]', sources TEXT,
  email_date TEXT, posted_hint TEXT,
  posted_at TEXT, date_confidence TEXT DEFAULT 'email',
  link_status TEXT DEFAULT 'unchecked',
  verified_at TEXT,
  filter_status TEXT DEFAULT 'pending',
  filter_reason TEXT DEFAULT '',
  match_score INTEGER, match_verdict TEXT, match_reasons TEXT, match_gaps TEXT, match_provider TEXT,
  first_seen TEXT, last_seen TEXT, notified_at TEXT
);
CREATE TABLE IF NOT EXISTS applications(
  job_id INTEGER PRIMARY KEY REFERENCES jobs(id),
  status TEXT NOT NULL, applied_date TEXT, link TEXT, notes TEXT DEFAULT '', updated_at TEXT
);
CREATE TABLE IF NOT EXISTS status_history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, status TEXT, changed_at TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS processed_emails(
  message_id TEXT PRIMARY KEY, source TEXT, processed_at TEXT, jobs_found INTEGER
);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT, stats TEXT
);
"""


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(d: dt.datetime | None) -> str | None:
    return d.astimezone(dt.timezone.utc).isoformat(timespec="seconds") if d else None


def parse_iso(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def connect(path=None) -> sqlite3.Connection:
    p = str(path) if path else str(C.db_path())
    if p != ":memory:":
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def find_duplicate(conn, fp, company_norm, title_norm, city_norm):
    row = conn.execute("SELECT * FROM jobs WHERE fingerprint=?", (fp,)).fetchone()
    if row:
        return row
    if not company_norm:
        return None
    for r in conn.execute("SELECT * FROM jobs WHERE company_norm=?", (company_norm,)):
        same_city = r["city_norm"] == city_norm or not r["city_norm"] or not city_norm
        if same_city and SequenceMatcher(None, r["title_norm"], title_norm).ratio() >= 0.88:
            return r
    return None


def upsert_job(conn, j: dict, now: dt.datetime | None = None):
    """Insert a job or merge it into an existing duplicate. Returns (job_id, is_new)."""
    ts = iso(now or now_utc())
    dup = find_duplicate(conn, j["fingerprint"], j["company_norm"], j["title_norm"], j["city_norm"])
    if dup:
        sources = {s for s in (dup["sources"] or "").split(",") if s} | {j["source"]}
        urls = json.loads(dup["urls_json"] or "[]")
        if j["url"] and j["url"] not in [u["url"] for u in urls]:
            urls.append({"source": j["source"], "url": j["url"]})
        desc = j["description"] if len(j["description"] or "") > len(dup["description"] or "") else dup["description"]
        hint = dup["posted_hint"] or j.get("posted_hint") or ""
        conn.execute(
            "UPDATE jobs SET sources=?, urls_json=?, description=?, posted_hint=?, last_seen=? WHERE id=?",
            (",".join(sorted(sources)), json.dumps(urls), desc, hint, ts, dup["id"]))
        # A hint-based date is better than a bare email date.
        if dup["date_confidence"] == "email" and j.get("date_confidence") == "hint":
            conn.execute("UPDATE jobs SET posted_at=?, date_confidence='hint', posted_hint=? WHERE id=?",
                         (j.get("posted_at"), j.get("posted_hint", ""), dup["id"]))
        conn.commit()
        return dup["id"], False
    cur = conn.execute(
        """INSERT INTO jobs(fingerprint, company_norm, title_norm, city_norm, title, company, location,
           description, url, urls_json, sources, email_date, posted_hint, posted_at, date_confidence,
           first_seen, last_seen)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (j["fingerprint"], j["company_norm"], j["title_norm"], j["city_norm"], j["title"], j["company"],
         j["location"], j["description"], j["url"], json.dumps([{"source": j["source"], "url": j["url"]}]),
         j["source"], j["email_date"], j.get("posted_hint", ""), j.get("posted_at"),
         j.get("date_confidence", "email"), ts, ts))
    conn.commit()
    return cur.lastrowid, True
