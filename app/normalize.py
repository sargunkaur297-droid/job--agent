"""Text / URL normalisation and fingerprints used for de-duplication."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlparse, urlunparse

_SUFFIX = re.compile(
    r"\b(pvt|private|ltd|limited|llp|inc|llc|corp|corporation|co|technologies|technology|"
    r"tech|solutions|services|india|software|systems)\b")


def norm_text(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9+#]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_company(s: str) -> str:
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", norm_text(s))).strip()


def norm_title(s: str) -> str:
    s = re.sub(r"\([^)]*\)", " ", s or "")
    return norm_text(s)


def fingerprint(company_norm: str, title_norm: str, city_norm: str) -> str:
    return hashlib.sha1(f"{company_norm}|{title_norm}|{city_norm}".encode()).hexdigest()


_LI = re.compile(r"/jobs/view/(?:[^/?]*?-)?(\d{6,})")


def canonical_url(url: str) -> str:
    """Strip tracking noise so the same posting always yields the same URL."""
    try:
        p = urlparse(url)
    except ValueError:
        return url
    host = p.netloc.lower()
    if "linkedin.com" in host:
        m = _LI.search(p.path)
        if m:
            return f"https://www.linkedin.com/jobs/view/{m.group(1)}"
    if "indeed." in host:
        q = parse_qs(p.query)
        jk = (q.get("jk") or q.get("vjk") or [None])[0]
        if jk:
            if host.split(".")[0] in ("cts", "click", "e", "mail"):
                host = "in.indeed.com"
            return f"https://{host}/viewjob?jk={jk}"
    if "naukri.com" in host:
        return urlunparse((p.scheme or "https", host, p.path, "", "", ""))
    return url
