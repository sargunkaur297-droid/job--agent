"""Indeed / LinkedIn / Naukri alert-email parsers."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..models import ParsedJob
from ..normalize import canonical_url
from .base import build, extract_blocks, pick_location

SALARY = re.compile(r"₹|\brs\.?\b|\blpa\b|a (year|month)|per (year|month)|\bctc\b", re.I)


def _host(href: str) -> str:
    try:
        return urlparse(href).netloc.lower()
    except ValueError:
        return ""


# ---------------------------------------------------------------- Indeed
def _indeed_href(h: str) -> bool:
    host = _host(h)
    return "indeed." in host and any(t in h for t in ("jk=", "/rc/clk", "/viewjob", "/pagead", "/v3/", "/m/"))


def parse_indeed(html: str) -> list[ParsedJob]:
    jobs = []
    for key, title, lines, href in extract_blocks(html, _indeed_href, canonical_url):
        rest = [l for l in lines if not SALARY.search(l)]
        if not rest:
            continue
        company = rest[0]
        location = pick_location(rest[1:]) or (rest[1] if len(rest) > 1 and len(rest[1]) < 50 else "")
        jobs.append(build("indeed", title, company, location, lines, canonical_url(href)))
    return jobs


# -------------------------------------------------------------- LinkedIn
def _li_href(h: str) -> bool:
    return "linkedin.com" in _host(h) and "/jobs/view/" in h


def parse_linkedin(html: str) -> list[ParsedJob]:
    jobs = []
    for key, title, lines, href in extract_blocks(html, _li_href, canonical_url):
        if not lines:
            continue
        first = lines[0]
        if "·" in first:
            company, _, location = (p.strip() for p in first.partition("·"))
        else:
            company = first
            location = pick_location(lines[1:]) or (lines[1] if len(lines) > 1 and len(lines[1]) < 60 else "")
        jobs.append(build("linkedin", title, company, location, lines[1:], canonical_url(href)))
    return jobs


# ---------------------------------------------------------------- Naukri
EXP = re.compile(r"\b\d+\s*(?:-|to)\s*\d+\s*yrs?\b|\b\d+\+?\s*yrs?\b", re.I)


def _nk_href(h: str) -> bool:
    return "naukri.com" in _host(h) and ("job-listings" in h or "/job-" in h or "jobId" in h)


def parse_naukri(html: str) -> list[ParsedJob]:
    jobs = []
    for key, title, lines, href in extract_blocks(html, _nk_href, canonical_url):
        rest = [l for l in lines if not SALARY.search(l)]
        if not rest:
            continue
        company = rest[0]
        location = pick_location(rest[1:])
        exp = next((l for l in rest if EXP.search(l)), "")
        extra = [exp] if exp and exp not in lines[1:] else []
        jobs.append(build("naukri", title, company, location, lines + extra, canonical_url(href)))
    return jobs


PARSERS = {"indeed": parse_indeed, "linkedin": parse_linkedin, "naukri": parse_naukri}


def parse_email(source: str, html: str) -> list[ParsedJob]:
    return [j for j in PARSERS[source](html) if j.title and j.url]
