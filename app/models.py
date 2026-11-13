"""Plain data containers shared across modules (no heavy imports)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class EmailMessage:
    id: str
    sender: str
    subject: str
    date: dt.datetime
    html: str = ""
    text: str = ""


@dataclass
class ParsedJob:
    source: str
    title: str
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    posted_hint: str = ""


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    text: str = ""
    error: str = ""


@dataclass
class MatchResult:
    score: int
    verdict: str
    reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    provider: str = "local"
