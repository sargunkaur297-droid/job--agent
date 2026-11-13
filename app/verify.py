"""Open job pages to read the real posting date and detect expired / broken links."""
from __future__ import annotations

import datetime as dt
import json
import re
import time

import requests

from .config import ROOT
from .dates import detect_expired, extract_page_info
from .db import iso, now_utc
from .models import FetchResult

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-IN,en;q=0.9",
}
BLOCKED = {401, 403, 429, 999, 503}


def http_fetch(url: str, timeout: int = 15) -> FetchResult:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        return FetchResult(r.url, r.status_code, r.text)
    except requests.RequestException as e:
        return FetchResult(url, 0, "", str(e)[:200])


def check_one(res: FetchResult, now: dt.datetime, tz: str) -> dict:
    """Interpret a fetched page -> {link_status, posted_at, description}."""
    if res.error or res.status_code == 0 or res.status_code in BLOCKED:
        return {"link_status": "unverifiable", "posted_at": None, "description": ""}
    info = extract_page_info(res.text, now, tz) if res.status_code == 200 else \
        {"posted_at": None, "description": "", "valid_through": None}
    bad = detect_expired(res.status_code, res.text, info["valid_through"], now)
    if bad:
        return {"link_status": bad, "posted_at": None, "description": ""}
    if res.status_code >= 400:
        return {"link_status": "broken", "posted_at": None, "description": ""}
    return {"link_status": "ok", "posted_at": info["posted_at"], "description": info["description"]}


def linkedin_guest_url(u: str) -> str | None:
    """Public (no-login) endpoint LinkedIn uses for logged-out job pages; often reachable when the normal page is blocked."""
    m = re.search(r"linkedin\.com/jobs/view/(?:[^/?]*?-)?(\d{6,})", u or "")
    return f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}" if m else None


def _attempt(use, u: str, v: dict, now, tz: str, can_sleep: bool) -> tuple[dict, int]:
    """Fetch+interpret one URL, retrying blocked/errored responses (and trying LinkedIn's guest page)."""
    calls, res = 1, check_one(use(u), now, tz)
    for _ in range(int(v.get("retries", 1))):
        if res["link_status"] != "unverifiable":
            break
        if can_sleep:
            time.sleep(v.get("retry_delay_seconds", 4))
        calls += 1
        res = check_one(use(u), now, tz)
    g = linkedin_guest_url(u) if v.get("linkedin_guest_fallback", True) else None
    if res["link_status"] == "unverifiable" and g:
        calls += 1
        res = check_one(use(g), now, tz)
    return res, calls


def verify_pending(conn, cfg: dict, fetcher=None, now: dt.datetime | None = None,
                   sleep: bool = True) -> dict:
    v = cfg["verification"]
    stats = {"checked": 0, "ok": 0, "expired": 0, "broken": 0, "unverifiable": 0, "dated": 0}
    if not v.get("fetch_pages", True):
        return stats
    now = now or now_utc()
    use = fetcher or (lambda u: http_fetch(u, v.get("timeout", 15)))
    rows = conn.execute(
        "SELECT * FROM jobs WHERE filter_status='pending' AND link_status='unchecked' "
        "ORDER BY first_seen DESC LIMIT ?", (v.get("max_per_run", 150),)).fetchall()
    for i, r in enumerate(rows, 1):
        if i % 10 == 0 or i == len(rows):
            print(f"      page {i}/{len(rows)}", flush=True)
        urls = [u["url"] for u in json.loads(r["urls_json"] or "[]")] or [r["url"]]
        result = {"link_status": "unverifiable", "posted_at": None, "description": ""}
        good_url = None
        for u in urls:
            result, calls = _attempt(use, u, v, now, cfg.get("timezone", "Asia/Kolkata"), sleep and fetcher is None)
            stats["checked"] += calls
            if sleep and fetcher is None:
                time.sleep(v.get("delay_seconds", 2.0))
            if result["link_status"] == "ok":
                good_url = u
            if result["link_status"] in ("ok", "expired"):
                break
        stats[result["link_status"]] += 1
        sets, args = ["link_status=?", "verified_at=?"], [result["link_status"], iso(now)]
        if result["posted_at"]:
            sets += ["posted_at=?", "date_confidence='page'"]
            args.append(iso(result["posted_at"]))
            stats["dated"] += 1
        if good_url and good_url != r["url"]:          # email/tracker should point at the link that actually opened
            sets.append("url=?")
            args.append(good_url)
        if len(result["description"] or "") > len(r["description"] or ""):
            sets.append("description=?")
            args.append(result["description"][:4000])
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", (*args, r["id"]))
    conn.commit()
    return stats
