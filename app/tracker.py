"""Application tracker. The app NEVER applies for you - you update statuses yourself."""
from __future__ import annotations

import datetime as dt

from .db import iso, now_utc

STATUSES = ["Shortlisted", "Not applied", "Applied", "Interview scheduled", "Rejected", "Offer received"]


def get(conn, job_id: int):
    return conn.execute("SELECT * FROM applications WHERE job_id=?", (job_id,)).fetchone()


def set_status(conn, job_id: int, status: str, applied_date: str | None = None,
               link: str | None = None, notes: str | None = None) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unknown status '{status}'. Use one of {STATUSES}")
    job = conn.execute("SELECT url FROM jobs WHERE id=?", (job_id,)).fetchone()
    if job is None:
        raise KeyError(f"No job with id {job_id}")
    cur = get(conn, job_id)
    if status == "Applied" and not applied_date and not (cur and cur["applied_date"]):
        applied_date = dt.date.today().isoformat()
    new = {
        "applied_date": applied_date or (cur["applied_date"] if cur else None),
        "link": link or (cur["link"] if cur else None) or job["url"],
        "notes": notes if notes is not None else (cur["notes"] if cur else ""),
    }
    ts = iso(now_utc())
    conn.execute(
        """INSERT INTO applications(job_id,status,applied_date,link,notes,updated_at) VALUES(?,?,?,?,?,?)
           ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, applied_date=excluded.applied_date,
           link=excluded.link, notes=excluded.notes, updated_at=excluded.updated_at""",
        (job_id, status, new["applied_date"], new["link"], new["notes"], ts))
    if not cur or cur["status"] != status:
        conn.execute("INSERT INTO status_history(job_id,status,changed_at,note) VALUES(?,?,?,?)",
                     (job_id, status, ts, new["notes"] or ""))
    conn.commit()


def ensure_shortlisted(conn, job_id: int) -> None:
    if get(conn, job_id) is None:
        set_status(conn, job_id, "Shortlisted")


def counts(conn) -> dict[str, int]:
    out = {s: 0 for s in STATUSES}
    for r in conn.execute("SELECT status, COUNT(*) n FROM applications GROUP BY status"):
        out[r["status"]] = r["n"]
    return out


def history(conn, job_id: int):
    return conn.execute("SELECT status, changed_at, note FROM status_history WHERE job_id=? ORDER BY id",
                        (job_id,)).fetchall()


def list_tracked(conn, status: str | None = None):
    q = """SELECT a.*, j.title, j.company, j.location, j.match_score, j.url AS job_url
           FROM applications a JOIN jobs j ON j.id=a.job_id"""
    args = ()
    if status:
        q += " WHERE a.status=?"
        args = (status,)
    return conn.execute(q + " ORDER BY a.updated_at DESC", args).fetchall()
