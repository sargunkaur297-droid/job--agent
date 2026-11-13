"""Relevance filtering: expiry, 24-hour window, location, role, level and experience."""
from __future__ import annotations

import datetime as dt
import re

from .db import parse_iso
from .locations import check_location

_EXP_PATTERNS = [
    re.compile(r"(\d+)\s*\+?\s*(?:-|to)\s*\d+\s*(?:years?|yrs?)", re.I),
    re.compile(r"(?:minimum|min\.?|at least)\s+(?:of\s+)?(\d+)\s*\+?\s*(?:years?|yrs?)", re.I),
    re.compile(r"(\d+)\s*\+\s*(?:years?|yrs?)", re.I),
    re.compile(r"(\d+)\s*(?:years?|yrs?)(?:\s+of)?\s+(?:relevant\s+|work\s+|industry\s+)?experience", re.I),
]


def _word(phrase: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(phrase.lower()), text) is not None


def required_years(text: str) -> int | None:
    vals = [int(m.group(1)) for p in _EXP_PATTERNS for m in p.finditer(text or "")]
    return min(vals) if vals else None


def evaluate(job: dict, cfg: dict, now: dt.datetime, cheap_only: bool = False) -> tuple[str, str]:
    """Return ('accepted'|'rejected', reason).
    cheap_only=True skips the link/date checks (used before opening job pages)."""
    prof, flt = cfg["profile"], cfg["filters"]
    title = (job.get("title") or "").lower()
    blob = f"{title} {(job.get('description') or '').lower()}"

    if not cheap_only:
        if flt.get("reject_expired", True) and job.get("link_status") in ("expired", "broken"):
            return "rejected", f"application link is {job['link_status']}"

        # --- strict posting-age check
        posted = parse_iso(job.get("posted_at"))
        conf = job.get("date_confidence") or "email"
        policy = flt.get("date_policy", "allow_hints")
        ok_conf = {"verified_only": {"page"}, "allow_hints": {"page", "hint"},
                   "allow_unverified": {"page", "hint", "email"}}.get(policy, {"page", "hint"})
        if conf not in ok_conf or not posted:
            return "rejected", f"posting date not verifiable (only '{conf}' date known, policy={policy})"
        age_h = (now - posted).total_seconds() / 3600
        if age_h > flt.get("max_age_hours", 24):
            return "rejected", f"posted {age_h:.0f}h ago (limit {flt.get('max_age_hours', 24)}h)"

    # --- location
    ok, city, why = check_location(job.get("location") or "", cfg["locations"],
                                   flt.get("unknown_location", "keep"))
    if not ok:
        return "rejected", why

    # --- role relevance
    if not any(_word(r, blob) for r in prof["target_roles"]):
        return "rejected", "title/description does not match any target role"
    bad = next((k for k in prof["avoid_title_keywords"] if _word(k, title)), None)
    if bad:
        return "rejected", f"title contains '{bad}' (seniority)"

    # --- experience / level
    yrs = required_years(blob)
    if yrs is not None and yrs > prof["max_experience_years"]:
        return "rejected", f"requires {yrs}+ years (max {prof['max_experience_years']})"
    if prof.get("require_level_signal"):
        has_level = any(_word(l, blob) for l in prof["levels"]) or (yrs is not None and yrs <= 1)
        if not has_level:
            return "rejected", "no entry-level / fresher signal"
    return "accepted", city and f"matched in {city}" or ""
