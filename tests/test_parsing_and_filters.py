import datetime as dt

from app.dates import detect_expired, extract_page_info, parse_hint
from app.filters import evaluate, required_years
from app.locations import check_location, detect_cities
from app.normalize import canonical_url, norm_company
from app.parsers import parse_email

from conftest import NOW, html


# ------------------------------------------------------------------ parsers
def test_indeed_parser_extracts_fields():
    jobs = parse_email("indeed", html("indeed"))
    assert len(jobs) == 4
    j = jobs[0]
    assert j.title == "Data Analyst Intern" and j.company.startswith("Acme")
    assert "Bengaluru" in j.location and "3 hours ago" in j.posted_hint
    assert j.url == "https://in.indeed.com/viewjob?jk=aaa111bbb222ccc3"


def test_linkedin_parser_splits_company_and_location():
    jobs = parse_email("linkedin", html("linkedin"))
    assert len(jobs) == 3
    assert jobs[0].company == "Acme Analytics" and "Bangalore" in jobs[0].location
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/3912345678"
    assert jobs[0].posted_hint == "2 hours ago"


def test_naukri_parser():
    jobs = parse_email("naukri", html("naukri"))
    assert len(jobs) == 3
    assert jobs[0].title.startswith("Data Analyst") and jobs[0].location == "Bengaluru"
    assert "0-1 Yrs" in jobs[0].description


def test_empty_email_gives_no_jobs():
    assert parse_email("indeed", "<html><body>Hello</body></html>") == []


# --------------------------------------------------------------- normalise
def test_canonical_urls_strip_tracking():
    a = canonical_url("https://www.linkedin.com/comm/jobs/view/123456789/?trackingId=x")
    b = canonical_url("https://www.linkedin.com/jobs/view/software-engineer-at-x-123456789?refId=y")
    assert a == b == "https://www.linkedin.com/jobs/view/123456789"


def test_company_suffixes_ignored():
    assert norm_company("Acme Analytics Pvt Ltd") == norm_company("Acme Analytics Private Limited")


# --------------------------------------------------------------- locations
def test_city_aliases():
    assert detect_cities("Bangalore Urban, Karnataka") == ["Bengaluru"]
    assert detect_cities("Gurgaon, Haryana") == ["Gurugram"]
    assert detect_cities("Work from home") == ["Remote"]


def test_location_filter():
    allowed = ["Bengaluru", "Pune", "Remote"]
    assert check_location("Pune, Maharashtra", allowed)[0] is True
    assert check_location("Kolkata", allowed)[0] is False
    assert check_location("India", allowed, "keep")[0] is True
    assert check_location("India", allowed, "reject")[0] is False
    assert check_location("Punekar Road Hamlet", allowed)[0] is False  # no partial-word match


# ------------------------------------------------------------------- dates
def test_parse_hint():
    assert parse_hint("3 hours ago", NOW) == NOW - dt.timedelta(hours=3)
    assert parse_hint("2 days ago", NOW) == NOW - dt.timedelta(days=2)
    assert parse_hint("Just posted", NOW) == NOW
    assert parse_hint("", NOW) is None


def test_page_date_from_jsonld():
    page = ('<html><script type="application/ld+json">{"@type":"JobPosting",'
            '"datePosted":"2026-11-13T09:00:00+05:30","description":"<p>Great role</p>"}</script></html>')
    info = extract_page_info(page, NOW)
    assert info["posted_at"] == dt.datetime(2026, 11, 13, 3, 30, tzinfo=dt.timezone.utc)
    assert info["description"] == "Great role"


def test_expiry_detection():
    assert detect_expired(200, "<p>This job has expired</p>") == "expired"
    assert detect_expired(404, "") == "broken"
    assert detect_expired(410, "") == "expired"
    assert detect_expired(200, "<p>Apply now</p>") is None
    assert detect_expired(200, "x", NOW - dt.timedelta(days=1), NOW) == "expired"


# ----------------------------------------------------------------- filters
def job(**kw):
    base = dict(title="Data Analyst Intern", description="python sql", location="Pune",
                posted_at=(NOW - dt.timedelta(hours=3)).isoformat(), date_confidence="hint",
                link_status="ok")
    base.update(kw)
    return base


def test_accepts_good_job(cfg):
    assert evaluate(job(), cfg, NOW)[0] == "accepted"


def test_strict_24h(cfg):
    assert evaluate(job(posted_at=(NOW - dt.timedelta(hours=23)).isoformat()), cfg, NOW)[0] == "accepted"
    st, why = evaluate(job(posted_at=(NOW - dt.timedelta(hours=25)).isoformat()), cfg, NOW)
    assert st == "rejected" and "25h" in why


def test_date_policies(cfg):
    email_only = job(date_confidence="email")
    assert evaluate(email_only, cfg, NOW)[0] == "accepted"            # default policy = allow_unverified
    cfg["filters"]["date_policy"] = "allow_hints"
    assert evaluate(email_only, cfg, NOW)[0] == "rejected"
    cfg["filters"]["date_policy"] = "allow_unverified"
    assert evaluate(email_only, cfg, NOW)[0] == "accepted"
    cfg["filters"]["date_policy"] = "verified_only"
    assert evaluate(job(date_confidence="hint"), cfg, NOW)[0] == "rejected"
    assert evaluate(job(date_confidence="page"), cfg, NOW)[0] == "accepted"


def test_expired_links_rejected(cfg):
    assert evaluate(job(link_status="expired"), cfg, NOW)[0] == "rejected"
    assert evaluate(job(link_status="broken"), cfg, NOW)[0] == "rejected"
    assert evaluate(job(link_status="unverifiable"), cfg, NOW)[0] == "accepted"


def test_role_seniority_experience(cfg):
    assert evaluate(job(title="Chef"), cfg, NOW)[0] == "rejected"
    assert "senior" in evaluate(job(title="Senior Data Analyst"), cfg, NOW)[1]
    assert evaluate(job(description="Requires 3+ years of experience"), cfg, NOW)[0] == "rejected"
    assert evaluate(job(description="0-1 years experience"), cfg, NOW)[0] == "accepted"


def test_required_level_signal(cfg):
    cfg["profile"]["require_level_signal"] = True
    assert evaluate(job(title="Data Analyst", description="sql"), cfg, NOW)[0] == "rejected"
    assert evaluate(job(title="Data Analyst Fresher"), cfg, NOW)[0] == "accepted"


def test_required_years():
    assert required_years("minimum 2 years") == 2
    assert required_years("1-3 yrs") == 1
    assert required_years("no mention") is None
