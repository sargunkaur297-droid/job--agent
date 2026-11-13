"""Shared helpers for turning job-alert HTML into ParsedJob objects."""
from __future__ import annotations

import re
from typing import Callable, Iterator

from bs4 import BeautifulSoup

from ..locations import detect_cities
from ..models import ParsedJob

GENERIC_LINK_TEXT = {
    "view job", "view jobs", "apply", "apply now", "easily apply", "view", "see job", "see jobs",
    "view all", "view all jobs", "see all jobs", "more", "unsubscribe", "learn more", "click here",
    "view details", "apply on company site", "view job details",
}
NOISE_LINES = GENERIC_LINK_TEXT | {"new", "be an early applicant", "actively recruiting", "easy apply",
                                   "promoted", "responsive employer", "urgently hiring", "hiring multiple candidates"}

HINT_RE = re.compile(
    r"just posted|posted today|active today|"
    r"\b\d+\+?\s*(?:minutes?|mins?|hours?|hrs?|days?|weeks?)\s*ago", re.I)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("‌", " ").replace("\xa0", " ")).strip()


def find_hint(lines: list[str]) -> str:
    for ln in lines:
        m = HINT_RE.search(ln)
        if m:
            return m.group(0)
    return ""


def extract_blocks(html: str, is_job_href: Callable[[str], bool],
                   canon: Callable[[str], str]) -> Iterator[tuple[str, str, list[str], str]]:
    """Yield (key, title, lines_without_title, href) for each distinct job link in the email."""
    soup = BeautifulSoup(html or "", "html.parser")
    groups: dict[str, list] = {}
    for a in soup.find_all("a", href=True):
        if is_job_href(a["href"]):
            groups.setdefault(canon(a["href"]), []).append(a)

    for key, anchors in groups.items():
        good = [a for a in anchors
                if clean(a.get_text()) and clean(a.get_text()).lower() not in GENERIC_LINK_TEXT]
        if not good:
            continue
        a = max(good, key=lambda x: len(clean(x.get_text())))
        title = clean(a.get_text())
        node = a
        for _ in range(8):
            parent = node.parent
            if parent is None or parent.name in ("body", "html", "[document]"):
                break
            others = any(k != key and any(parent in y.parents for y in al) for k, al in groups.items())
            if others:
                break
            node = parent
        lines = []
        for s in node.stripped_strings:
            c = clean(s)
            if not c or c == title or c.lower() in NOISE_LINES:
                continue
            lines.append(c)
        yield key, title, lines[:14], a["href"]


def pick_location(lines: list[str]) -> str:
    for ln in lines:
        if detect_cities(ln) and len(ln) < 80:
            return ln
    return ""


def build(source: str, title: str, company: str, location: str, lines: list[str], url: str) -> ParsedJob:
    return ParsedJob(
        source=source, title=title, company=company, location=location,
        description=" ".join(l for l in lines if l not in (company, location))[:900],
        url=url, posted_hint=find_hint(lines))
