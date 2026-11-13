"""Job digest email (HTML).

Every job that passed your rules and was posted inside the time window is listed - no score cut-off.
Each row has: role (clickable link), company, location, source, how old it is, and link status.
Large lists are packed into as few emails as possible (default 150 jobs per email, auto-split if an
email would get near Gmail's ~102 KB "message clipped" limit).
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
from collections import Counter
from zoneinfo import ZoneInfo

from .config import ROOT
from .db import iso, now_utc, parse_iso

GMAIL_SAFE_BYTES = 90_000          # Gmail clips bodies above ~102 KB
SRC_LABEL = {"linkedin": "LinkedIn", "naukri": "Naukri", "indeed": "Indeed"}


def pending_jobs(conn, cfg: dict, now: dt.datetime | None = None):
    """All accepted jobs inside the window, newest first.
    mode 'last_24h' (default): every matching job of the window, even if already emailed earlier.
    mode 'new_only': only jobs never emailed before."""
    n, f = cfg["notifications"], cfg["filters"]
    now = now or now_utc()
    since = iso(now - dt.timedelta(hours=f.get("max_age_hours", 24)))
    q = "SELECT * FROM jobs WHERE filter_status='accepted' AND posted_at>=?"
    if n.get("mode", "last_24h") == "new_only":
        q += " AND notified_at IS NULL"
    q += " ORDER BY posted_at DESC, id DESC"
    args: list = [since]
    limit = int(n.get("max_jobs_in_digest") or 0)
    if limit > 0:
        q += " LIMIT ?"
        args.append(limit)
    return conn.execute(q, args).fetchall()


def source_health(conn, cfg: dict, now: dt.datetime) -> list[str]:
    """Warnings when a platform sent no alert emails, or emails were read but nothing could be parsed."""
    days = cfg["gmail"].get("lookback_days", 2)
    since = iso(now - dt.timedelta(days=days))
    got = {r["source"]: (r["n"], r["jobs"] or 0) for r in conn.execute(
        "SELECT source, COUNT(*) n, SUM(jobs_found) jobs FROM processed_emails WHERE processed_at>=? GROUP BY source",
        (since,))}
    out = []
    for src in cfg["gmail"]["queries"]:
        n, j = got.get(src, (0, 0))
        label = SRC_LABEL.get(src, src)
        if n == 0:
            out.append(f"{label}: no alert emails received in the last {days} days. Check that the {label} job alert "
                       f"is active and sent to this Gmail.")
        elif j == 0:
            out.append(f"{label}: {n} alert email(s) read but 0 jobs found. The email layout may have changed "
                       f"(parser needs an update).")
    return out


def filtered_out(conn, cfg: dict, now: dt.datetime):
    since = iso(now - dt.timedelta(hours=cfg["filters"].get("max_age_hours", 24)))
    return conn.execute(
        "SELECT title, company, location, url, filter_reason FROM jobs WHERE filter_status='rejected' "
        "AND first_seen>=? ORDER BY first_seen DESC, id DESC", (since,)).fetchall()


def _warn_html(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
    return (f"<div style='background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;padding:8px 12px;margin:10px 0'>"
            f"<b>Check this:</b><ul style='margin:4px 0'>{items}</ul></div>")


def _filtered_html(rej, limit: int) -> str:
    if not rej:
        return ""
    esc = html.escape
    groups = Counter(re.sub(r"\d+", "N", r["filter_reason"] or "other") for r in rej).most_common(8)
    summary = "".join(f"<li>{n} &times; {esc(reason)}</li>" for reason, n in groups)
    shown = rej[:max(0, limit)]
    items = "".join(
        f"<li style='margin:2px 0'><a href='{esc(r['url'] or '#')}'>{esc(r['title'])}</a> - {esc(r['company'] or '')} - "
        f"{esc(r['location'] or 'n/a')} <i style='color:#9a3412'>({esc(r['filter_reason'] or '')})</i></li>"
        for r in shown)
    more = f"<li><i>+ {len(rej) - len(shown)} more not listed</i></li>" if len(rej) > len(shown) else ""
    return (f"<h3 style='margin-top:28px'>Filtered out by your rules ({len(rej)})</h3>"
            f"<p style='color:#4b5563;margin-top:0'>Not in the list above. If something here looks right for you, "
            f"loosen that rule in config.yaml.</p><ul style='font-size:13px'>{summary}</ul>"
            f"<ul style='font-size:12px;color:#374151'>{items}{more}</ul>")


def _age(j, now: dt.datetime) -> str:
    p = parse_iso(j["posted_at"])
    if not p:
        return "?"
    h = max(0, (now - p).total_seconds() / 3600)
    return f"{int(h * 60)}m ago" if h < 1 else f"{int(h)}h ago"


def _row(i: int, j, now: dt.datetime) -> str:
    esc = html.escape
    where = j["location"] or j["canonical_location"] or "Not specified"
    urls = json.loads(j["urls_json"] or "[]")
    srcs = [s for s in (j["sources"] or "").split(",") if s]
    primary = j["url"] or (urls[0]["url"] if urls else "#")
    also = " ".join(f'<a href="{esc(u["url"])}">{esc(SRC_LABEL.get(u["source"], u["source"]))}</a>'
                    for u in urls if u["url"] != primary)
    first = SRC_LABEL.get(next((u["source"] for u in urls if u["url"] == primary), srcs[0] if srcs else ""), "")
    link_note = ("&#10003;" if j["link_status"] == "ok" else
                 "<span style='color:#b45309' title='Site blocks automatic checking - open to confirm'>?</span>")
    est = "" if j["date_confidence"] == "page" else "~"
    return (f"<tr><td style='padding:6px;border-bottom:1px solid #e5e7eb'>{i}</td>"
            f"<td style='padding:6px;border-bottom:1px solid #e5e7eb'>"
            f"<a href='{esc(primary)}' style='font-weight:600;color:#1d4ed8'>{esc(j['title'])}</a>"
            f"<div style='font-size:12px;color:#6b7280'>{esc(j['company'] or '')}</div></td>"
            f"<td style='padding:6px;border-bottom:1px solid #e5e7eb'>{esc(where)}</td>"
            f"<td style='padding:6px;border-bottom:1px solid #e5e7eb;font-size:12px'>"
            f"<a href='{esc(primary)}'>{esc(first)}</a>{(' + ' + also) if also else ''}</td>"
            f"<td style='padding:6px;border-bottom:1px solid #e5e7eb;font-size:12px;white-space:nowrap'>"
            f"{est}{_age(j, now)} {link_note}</td></tr>")


def build_digest(jobs, name: str = "", now: dt.datetime | None = None, tz: str = "Asia/Kolkata",
                 part: int = 1, parts: int = 1, total: int | None = None, hours: int = 24,
                 stats: dict | None = None, start: int = 1,
                 warnings: list[str] | None = None, extra_html: str = "") -> tuple[str, str]:
    now = now or now_utc()
    today = now.astimezone(ZoneInfo(tz)).strftime("%d %b %Y")
    total = len(jobs) if total is None else total
    suffix = f" ({part}/{parts})" if parts > 1 else ""
    if not jobs:
        info = ""
        if stats and "ingest" in stats:
            ing = stats["ingest"]
            info = (f"<p style='color:#6b7280'>Scan details: {ing.get('emails', 0)} new alert email(s) read, "
                    f"{ing.get('jobs_parsed', 0)} job(s) found in them.</p>")
        body = (f"<div style='font-family:Arial,sans-serif;max-width:760px;margin:auto'>"
                f"<h2>Hi {html.escape(name or 'there')} - no matching jobs in the last {hours}h</h2>"
                f"<p>The scan ran fine but no listing that follows your rules was found. Check that your Indeed, "
                f"LinkedIn and Naukri job alerts are active and reach this Gmail inbox.</p>"
                f"{_warn_html(warnings or [])}{info}{extra_html}</div>")
        return f"Job Agent: 0 jobs in the last {hours}h - {today}", body
    subject = f"Job Agent: {total} job(s) from the last {hours}h - {today}{suffix}"
    rows = "".join(_row(i, j, now) for i, j in enumerate(jobs, start))
    body = (f"<div style='font-family:Arial,sans-serif;max-width:860px;margin:auto'>"
            f"<h2 style='margin-bottom:4px'>Hi {html.escape(name or 'there')} - {total} job(s) posted in the last {hours}h</h2>"
            f"<p style='margin-top:0;color:#4b5563'>Every listing that matches your rules, newest first. "
            f"Click the role to open it. &#10003; = link checked and open; <b style='color:#b45309'>?</b> = the site "
            f"blocks automatic checks, so open it to confirm; ~ = age estimated from the alert email. "
            f"Nothing is applied for automatically.</p>{_warn_html(warnings or [])}"
            f"<table style='border-collapse:collapse;width:100%;font-size:14px'>"
            f"<tr style='background:#f3f4f6;text-align:left'><th style='padding:6px'>#</th><th style='padding:6px'>Role / Company</th>"
            f"<th style='padding:6px'>Location</th><th style='padding:6px'>Source</th><th style='padding:6px'>Posted</th></tr>"
            f"{rows}</table>{extra_html}</div>")
    return subject, body


def _chunks(jobs: list, size: int):
    for i in range(0, len(jobs), size):
        yield jobs[i:i + size]


def send_digest(conn, cfg: dict, sender=None, now: dt.datetime | None = None, stats: dict | None = None) -> dict:
    n = cfg["notifications"]
    now = now or now_utc()
    tz = cfg.get("timezone", "Asia/Kolkata")
    hours = cfg["filters"].get("max_age_hours", 24)
    name = cfg["profile"].get("name", "")
    jobs = list(pending_jobs(conn, cfg, now))
    if not jobs and not n.get("send_empty_digest", True):
        return {"sent": 0, "emails": 0, "reason": "no matching jobs"}

    # Pack into emails: up to jobs_per_email each, split further if the HTML would be too large.
    per = max(1, int(n.get("jobs_per_email", 150)))
    batches: list[list] = []
    todo = list(_chunks(jobs, per)) or [[]]
    while todo:
        b = todo.pop(0)
        _, body = build_digest(b, name, now, tz, hours=hours)
        if len(body.encode("utf-8")) > GMAIL_SAFE_BYTES and len(b) > 1:
            half = len(b) // 2
            todo[0:0] = [b[:half], b[half:]]
        else:
            batches.append(b)

    ROOT.joinpath("data").mkdir(parents=True, exist_ok=True)
    warnings = source_health(conn, cfg, now) if n.get("show_source_warnings", True) else []
    rej = filtered_out(conn, cfg, now) if n.get("show_filtered_out", True) else []
    emails, sent_jobs = [], 0
    done = 0
    for k, b in enumerate(batches, 1):
        last = k == len(batches)
        limit = int(n.get("filtered_out_max", 60))
        while True:                                   # shrink the "filtered out" list until the email fits in Gmail
            extra = _filtered_html(rej, limit) if last else ""
            subject, body = build_digest(b, name, now, tz, part=k, parts=len(batches), total=len(jobs),
                                         hours=hours, stats=stats, start=done + 1,
                                         warnings=warnings if k == 1 else None, extra_html=extra)
            if len(body.encode("utf-8")) <= GMAIL_SAFE_BYTES or not extra or limit <= 0:
                break
            limit = limit // 2
        done += len(b)
        if k == 1:
            ROOT.joinpath("data", "last_digest.html").write_text(body, encoding="utf-8")
        emails.append((subject, body, b))
    if not n.get("send_email") or sender is None:
        return {"sent": 0, "emails": 0, "jobs": len(jobs),
                "reason": "email disabled; digest saved to data/last_digest.html"}
    ts = iso(now)
    for subject, body, b in emails:
        sender(n.get("to", ""), subject, body)
        conn.executemany("UPDATE jobs SET notified_at=? WHERE id=?", [(ts, j["id"]) for j in b])
        conn.commit()
        sent_jobs += len(b)
    return {"sent": sent_jobs, "emails": len(emails), "reason": "ok"}
