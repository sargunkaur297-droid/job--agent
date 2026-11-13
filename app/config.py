"""Configuration: built-in defaults < config.yaml < environment variables."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULTS: dict = {
    "timezone": "Asia/Kolkata",
    "profile": {
        "name": "",
        "graduation_year": None,
        "target_roles": [
            "data analyst", "data analytics", "business analyst", "data scientist",
            "data engineer", "machine learning", "python developer", "software engineer",
            "software developer", "sde", "backend", "full stack", "fullstack",
            "web developer", "frontend", "java developer", "qa engineer",
            "test engineer", "devops", "cloud engineer", "ai engineer",
        ],
        "skills": [],
        "levels": ["intern", "internship", "trainee", "fresher", "freshers", "graduate",
                   "entry level", "entry-level", "junior", "associate", "apprentice"],
        "max_experience_years": 1,
        "avoid_title_keywords": ["senior", "sr", "lead", "manager", "principal", "director",
                                 "architect", "head", "vp", "staff"],
        "require_level_signal": False,
        "notes": "",
    },
    "locations": ["Bengaluru", "Hyderabad", "Pune", "Mumbai", "Chennai", "Noida",
                  "Delhi", "Gurugram", "Mohali", "Remote"],
    "filters": {
        "max_age_hours": 24,
        "date_policy": "allow_unverified",
        "unknown_location": "keep",
        "reject_expired": True,
    },
    "gmail": {
        "lookback_days": 2,
        "max_emails_per_source": 200,
        "queries": {
            "indeed": "from:indeed.com newer_than:{days}d",
            "linkedin": "from:linkedin.com newer_than:{days}d",
            "naukri": "from:naukri.com newer_than:{days}d",
        },
    },
    "verification": {"fetch_pages": True, "delay_seconds": 1.0, "timeout": 15, "max_per_run": 500,
                     "retries": 1, "retry_delay_seconds": 4, "linkedin_guest_fallback": True},
    "matching": {
        "enabled": False,            # True = also compute an AI score (used for sorting only, never to drop jobs)
        "provider": "gemini", "model": "gemini-2.5-flash",
        "min_score_to_shortlist": 0, "max_jobs_per_run": 60, "delay_seconds": 4.0,
    },
    "notifications": {
        "send_email": True, "to": "",
        "mode": "last_24h",          # last_24h = every matching job of the last 24h in each email | new_only
        "max_jobs_in_digest": 0,     # 0 = no limit
        "jobs_per_email": 150,       # one email holds up to this many jobs (auto-split if too large for Gmail)
        "send_empty_digest": True,   # always email you, even when the scan found nothing
        "show_source_warnings": True,   # warn when a platform sent no alerts / parser found 0 jobs
        "show_filtered_out": True,      # list what your rules filtered out (with the reason) at the end
        "filtered_out_max": 60,
    },
}


def _merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path or os.getenv("JOB_AGENT_CONFIG") or ROOT / "config.yaml")
    cfg = copy.deepcopy(DEFAULTS)
    if p.exists():
        _merge(cfg, yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    return cfg


def db_path() -> Path:
    return Path(os.getenv("JOB_AGENT_DB") or ROOT / "data" / "jobs.db")


def save_user_config(updates: dict, path: str | os.PathLike | None = None) -> None:
    """Merge `updates` into config.yaml (keeps a config.yaml.bak backup). Comments are not preserved."""
    p = Path(path or os.getenv("JOB_AGENT_CONFIG") or ROOT / "config.yaml")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    if p.exists():
        p.with_suffix(".yaml.bak").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    _merge(raw or {}, updates)
    p.write_text("# Edited via the dashboard Settings tab (you can also edit by hand).\n"
                 + yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")


def save_env_var(name: str, value: str) -> None:
    """Write/replace NAME=value in .env (created if missing) and apply it to the running process now."""
    p = ROOT / ".env"
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    new, done = [], False
    for ln in lines:
        if ln.strip().startswith(f"{name}=") or ln.strip().startswith(f"# {name}="):
            if not done:
                new.append(f"{name}={value}")
                done = True
            continue
        new.append(ln)
    if not done:
        new.append(f"{name}={value}")
    p.write_text("\n".join(new) + "\n", encoding="utf-8")
    os.environ[name] = value
