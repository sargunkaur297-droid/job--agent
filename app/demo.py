"""Offline demo data so you can try the whole app without Gmail."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .config import ROOT
from .models import EmailMessage


def demo_messages(now: dt.datetime | None = None) -> dict[str, list[EmailMessage]]:
    now = now or dt.datetime.now(dt.timezone.utc)
    out = {}
    for src in ("indeed", "linkedin", "naukri"):
        html = (ROOT / "sample_emails" / f"{src}.html").read_text(encoding="utf-8")
        out[src] = [EmailMessage(f"demo-{src}", f"{src} alerts", f"{src} jobs", now, html=html)]
    return out
