"""City detection and location filtering."""
from __future__ import annotations

import re

CITY_ALIASES: dict[str, list[str]] = {
    "Bengaluru": ["bengaluru", "bangalore", "bengalooru"],
    "Hyderabad": ["hyderabad", "secunderabad", "hyd"],
    "Pune": ["pune", "pimpri", "chinchwad"],
    "Mumbai": ["mumbai", "navi mumbai", "thane", "bombay"],
    "Chennai": ["chennai", "madras"],
    "Noida": ["noida", "greater noida"],
    "Delhi": ["delhi", "new delhi", "delhi ncr", "ncr"],
    "Gurugram": ["gurugram", "gurgaon"],
    "Mohali": ["mohali", "sas nagar", "sahibzada ajit singh nagar"],
    "Remote": ["remote", "work from home", "wfh", "work-from-home"],
}

_VAGUE = {"", "india", "pan india", "multiple locations", "anywhere", "multiple", "various"}


def _patterns(extra=()):
    aliases = {k: list(v) for k, v in CITY_ALIASES.items()}
    for name in extra:
        aliases.setdefault(name, [name.lower()])
    return {
        c: re.compile(r"(?<![a-z])(?:%s)(?![a-z])" % "|".join(
            re.escape(a) for a in sorted(set(v), key=len, reverse=True)), re.I)
        for c, v in aliases.items()
    }


def detect_cities(text: str, extra=()) -> list[str]:
    """Canonical city names found in text, in order of appearance."""
    if not text:
        return []
    hits = []
    for city, pat in _patterns(tuple(extra)).items():
        m = pat.search(text)
        if m:
            hits.append((m.start(), city))
    return [c for _, c in sorted(hits)]


def check_location(text: str, allowed: list[str], unknown_policy: str = "keep"):
    """Return (ok, canonical_city, reason)."""
    cities = detect_cities(text, allowed)
    for c in cities:
        if c in allowed:
            return True, c, ""
    clean = re.sub(r"[^a-z ]", " ", (text or "").lower()).strip()
    clean = re.sub(r"\s+", " ", clean)
    if clean in _VAGUE:
        return unknown_policy == "keep", "", "location unknown"
    return False, (cities[0] if cities else ""), f"location '{text.strip()}' is not in your target cities"
