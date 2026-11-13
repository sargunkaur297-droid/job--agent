# Project Report: Job Agent

## 1. Problem
Job seekers get hundreds of alert emails daily across Indeed, LinkedIn and Naukri. Most are duplicates, stale,
in the wrong city or too senior. Finding the few worthwhile, still-open postings is slow manual work.

## 2. Objective
Automatically surface jobs that are new (≤ 24 h), open, in target cities, relevant to the candidate's profile,
ranked by resume fit, while keeping the human in control of every application.

## 3. Approach
1. **Ingestion** - Gmail API reads alert emails; platform-specific parsers extract structured jobs.
2. **De-duplication** - fingerprint of normalised company + title + city, plus fuzzy title match; merged jobs keep all links.
3. **Verification** - job page is opened to read the real posting date and detect expired or broken links.
4. **Filtering** - strict age window, city aliases, role/seniority/experience rules, each with a recorded reason.
5. **AI matching** - Gemini returns score, reasons and gaps; a transparent keyword scorer is the offline fallback.
6. **Tracking and UI** - six-status tracker; Streamlit dashboard with filters, details and manual updates.
7. **Automation** - GitHub Actions cron or local scheduler; digest email with per-job notification memory.

## 4. Technology
Python 3.11, SQLite, BeautifulSoup, Requests, Gmail API (OAuth), Google Gemini (`google-genai`),
Streamlit, pandas, pytest, GitHub Actions.

## 5. Testing
28 automated tests cover: parsers for all three sources, URL/company normalisation, location aliases,
date hints and JSON-LD dates, expiry detection, 24 h boundaries, date policies, seniority/experience rules,
duplicate merging, idempotent reruns, ranking, tracker transitions and history, and notification de-duplication.
The dashboard was smoke-tested with Streamlit's AppTest. Live Gmail, Gemini and real job sites are not
exercised by the automated tests, so run the app once with your own accounts and check the first digest.

## 6. Limitations and future work
- Parsers depend on email templates, which can change.
- Job sites may block page verification; such jobs are flagged *unverifiable*.
- Possible extensions: Telegram alerts, resume-tailored cover-letter drafts (still manual approval), more sources.

## 7. Conclusion
The system turns a noisy inbox into a short, ranked, explainable shortlist and a tracker, saving daily
screening time while the candidate stays in control of applying.
