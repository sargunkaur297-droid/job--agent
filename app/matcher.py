"""Job <-> resume matching. Gemini (with automatic local fallback) or a local scorer."""
from __future__ import annotations

import json
import re
import time

from .filters import _word, required_years
from .models import MatchResult
from .resume import detect_skills


def verdict_for(score: int) -> str:
    return "Strong match" if score >= 80 else "Good match" if score >= 65 else \
        "Possible match" if score >= 50 else "Weak match"


class LocalMatcher:
    """Transparent keyword scorer: role fit + skill overlap + entry-level fit."""
    name = "local"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def score(self, job: dict, resume_text: str) -> MatchResult:
        prof = self.cfg["profile"]
        title = (job.get("title") or "").lower()
        blob = f"{title} {(job.get('description') or '').lower()}"
        my_skills = set(detect_skills(resume_text, prof.get("skills", [])))
        job_skills = set(detect_skills(blob))
        reasons, gaps, score = [], [], 15

        roles = [r for r in prof["target_roles"] if _word(r, title)]
        if roles:
            score += 30
            reasons.append(f"Title matches your target role '{roles[0]}'")
        elif any(_word(r, blob) for r in prof["target_roles"]):
            score += 15
            reasons.append("Description mentions one of your target roles")

        overlap = sorted(my_skills & job_skills)
        if job_skills:
            ratio = len(overlap) / min(len(job_skills), 8)
            score += int(min(1.0, ratio) * 35)
            if overlap:
                reasons.append("Skills you have: " + ", ".join(overlap[:8]))
            missing = sorted(job_skills - my_skills)
            if missing:
                gaps.append("Skills not found on your resume: " + ", ".join(missing[:6]))
        elif my_skills:
            score += 10
            reasons.append("Job lists no specific skills; neutral skill fit")

        if any(_word(l, blob) for l in prof["levels"]):
            score += 12
            reasons.append("Entry-level / fresher friendly")
        yrs = required_years(blob)
        if yrs is not None and yrs > prof["max_experience_years"]:
            score -= 25
            gaps.append(f"Asks for {yrs}+ years of experience")
        if job.get("canonical_location"):
            score += 8
            reasons.append(f"Located in {job['canonical_location']}")
        if not my_skills:
            gaps.append("No resume detected - add one to resume/ for better scores")
        score = max(0, min(100, score))
        return MatchResult(score, verdict_for(score), reasons, gaps, "local")


PROMPT = """You are a careful recruiter assistant. Score how well this job fits the candidate.

CANDIDATE PROFILE
Name: {name} | Graduation year: {grad}
Target roles: {roles}
Extra notes: {notes}

RESUME
{resume}

JOB
Title: {title}
Company: {company}
Location: {location}
Description: {desc}

Return ONLY JSON: {{"score": <0-100 integer>, "reasons": [<up to 4 short strings why it matches>],
"gaps": [<up to 4 short strings on what is missing or risky>]}}
Be strict: 80+ only if skills AND level AND role all fit. Entry-level / intern fit matters."""


class GeminiMatcher:
    name = "gemini"

    def __init__(self, cfg: dict, api_key: str):
        from google import genai
        self.cfg = cfg
        self.client = genai.Client(api_key=api_key)
        self.model = cfg["matching"]["model"]
        self.fallback = LocalMatcher(cfg)

    def score(self, job: dict, resume_text: str) -> MatchResult:
        from google.genai import types
        p = self.cfg["profile"]
        prompt = PROMPT.format(
            name=p.get("name", ""), grad=p.get("graduation_year", ""), roles=", ".join(p["target_roles"][:15]),
            notes=p.get("notes", ""), resume=(resume_text or "(no resume provided)")[:6000],
            title=job.get("title", ""), company=job.get("company", ""), location=job.get("location", ""),
            desc=(job.get("description") or "")[:3000])
        for attempt in range(2):
            try:
                resp = self.client.models.generate_content(
                    model=self.model, contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2))
                data = json.loads(re.sub(r"^```(?:json)?|```$", "", (resp.text or "").strip(), flags=re.M))
                score = max(0, min(100, int(data["score"])))
                return MatchResult(score, verdict_for(score), [str(x) for x in data.get("reasons", [])][:4],
                                   [str(x) for x in data.get("gaps", [])][:4], "gemini")
            except Exception as e:
                print(f"[gemini] attempt {attempt + 1} failed: {str(e)[:120]}")
                time.sleep(5 * (attempt + 1))
        r = self.fallback.score(job, resume_text)
        r.provider = "local (gemini failed)"
        return r


def make_matcher(cfg: dict, api_key: str | None):
    if cfg["matching"]["provider"] == "gemini" and api_key:
        try:
            return GeminiMatcher(cfg, api_key)
        except Exception as e:
            print(f"[matcher] Gemini unavailable ({e}); using local matcher")
    elif cfg["matching"]["provider"] == "gemini":
        print("[matcher] GEMINI_API_KEY not set; using local matcher")
    return LocalMatcher(cfg)
