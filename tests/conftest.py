import datetime as dt
from pathlib import Path

import pytest

from app import db
from app.config import load_config
from app.models import EmailMessage

SAMPLES = Path(__file__).resolve().parent.parent / "sample_emails"
NOW = dt.datetime(2026, 11, 13, 6, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def cfg():
    c = load_config("/nonexistent.yaml")  # pure defaults, independent of the user's config.yaml
    c["verification"]["fetch_pages"] = False
    c["matching"]["delay_seconds"] = 0
    return c


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def html(name: str) -> str:
    return (SAMPLES / f"{name}.html").read_text(encoding="utf-8")


@pytest.fixture
def messages():
    return {s: [EmailMessage(f"m-{s}", s, s, NOW, html=html(s))] for s in ("indeed", "linkedin", "naukri")}
