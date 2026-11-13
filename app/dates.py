"""Posting-date and expiry detection."""
from __future__ import annotations

import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

EXPIRED_PHRASES = [
    "no longer accepting applications", "this job has expired", "job has expired",
    "this job is no longer available", "job is no longer available", "no longer available",
    "position has been filled", "this position has been filled", "job posting has expired",
    "this job posting is no longer", "vacancy has expired", "job you are looking for is no longer",
    "the job you were looking for", "applications are closed", "closed for applications",
    "no longer open", "page not found",
]

_UNITS = {"minute": 1 / 60, "min": 1 / 60, "hour": 1, "hr": 1, "day": 24, "week": 168}


def parse_hint(hint: str, ref: dt.datetime) -> dt.datetime | None:
    """'2 hours ago' / 'Just posted' -> absolute datetime relative to `ref`."""
    h = (hint or "").lower()
    if not h:
        return None
    if "just posted" in h or "posted today" in h or "active today" in h:
        return ref
    m = re.search(r"(\d+)\+?\s*(minute|min|hour|hr|day|week)s?", h)
    if not m:
        return None
    return ref - dt.timedelta(hours=int(m.group(1)) * _UNITS[m.group(2)])


def _parse_iso(value: str, tz: ZoneInfo) -> dt.datetime | None:
    v = (value or "").strip().replace("Z", "+00:00")
    if not v:
        return None
    try:
        d = dt.datetime.fromisoformat(v)
    except ValueError:
        for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                d = dt.datetime.strptime(v, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if len(v) <= 10 or (d.hour == 0 and d.minute == 0 and "T" not in v and ":" not in v):
        d = d.replace(hour=12)  # date-only: assume midday local (+/- 12h accuracy)
    if d.tzinfo is None:
        d = d.replace(tzinfo=tz)
    return d.astimezone(dt.timezone.utc)


def _jobposting_nodes(obj):
    if isinstance(obj, list):
        for x in obj:
            yield from _jobposting_nodes(x)
    elif isinstance(obj, dict):
        t = obj.get("@type")
        if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
            yield obj
        for v in obj.values():
            if isinstance(v, (list, dict)):
                yield from _jobposting_nodes(v)


def extract_page_info(html: str, now: dt.datetime, tz_name: str = "Asia/Kolkata") -> dict:
    """Return {'posted_at': datetime|None, 'description': str, 'valid_through': datetime|None}."""
    tz = ZoneInfo(tz_name)
    soup = BeautifulSoup(html or "", "html.parser")
    posted = valid = None
    desc = ""
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or s.get_text() or "")
        except (ValueError, TypeError):
            continue
        for node in _jobposting_nodes(data):
            posted = posted or _parse_iso(str(node.get("datePosted", "")), tz)
            valid = valid or _parse_iso(str(node.get("validThrough", "")), tz)
            if node.get("description") and not desc:
                desc = BeautifulSoup(str(node["description"]), "html.parser").get_text(" ", strip=True)
    if not posted:
        for attrs in ({"itemprop": "datePosted"}, {"property": "article:published_time"},
                      {"name": "datePosted"}):
            tag = soup.find(attrs=attrs)
            if tag:
                posted = _parse_iso(tag.get("content") or tag.get("datetime") or tag.get_text(), tz)
                if posted:
                    break
    if not posted:
        text = soup.get_text(" ", strip=True)
        m = re.search(r"(?:posted|date posted)[:\s]+(?:on\s+)?(\d+\+?\s*(?:minutes?|mins?|hours?|hrs?|days?|weeks?)\s*ago|today|just now)", text, re.I)
        if m:
            posted = parse_hint(m.group(1), now) if "ago" in m.group(1).lower() else now
        else:
            m = re.search(r"posted (?:on )?(\d{1,2} [A-Za-z]{3,9} \d{4})", text, re.I)
            if m:
                posted = _parse_iso(m.group(1), tz)
    if not desc:
        body = soup.find("body")
        desc = (body.get_text(" ", strip=True) if body else "")[:3000]
    return {"posted_at": posted, "description": desc, "valid_through": valid}


def detect_expired(status_code: int, text: str, valid_through: dt.datetime | None = None,
                   now: dt.datetime | None = None) -> str | None:
    """Return 'expired', 'broken' or None."""
    if status_code == 410:
        return "expired"
    if status_code == 404:
        return "broken"
    if valid_through and now and valid_through < now:
        return "expired"
    low = (text or "").lower()
    head = low[:6000]
    if any(p in head for p in EXPIRED_PHRASES):
        return "expired"
    return None
