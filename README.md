# Job Agent

A Gmail-powered job-alert assistant that collects Indeed, LinkedIn and Naukri alerts, parses and deduplicates listings, checks posting links, filters roles by your criteria, sends a digest, and provides a Streamlit application tracker.

> **Safety first:** This repository is public. Never commit your Gmail OAuth files, API keys, resume, personal job database, or a personalised configuration file. The committed `config.yaml` contains only public-safe defaults.

## Features

- Gmail API integration using OAuth (no Gmail password storage)
- Job-alert parsing, normalisation and duplicate detection
- Posting/link verification and configurable role, location and experience filters
- Optional Gemini-based relevance scoring
- Streamlit dashboard with job filters and application tracking
- Email digest notifications
- Automated tests

The app does not apply to jobs automatically. You review each listing and apply yourself.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.run_daily --demo
streamlit run dashboard.py
```

On Windows, use `copy .env.example .env` instead of `cp`.

## Personal setup

1. Configure Gmail API and create a Google OAuth **Desktop app** credential.
2. Save the downloaded file locally as `credentials.json` (never commit it).
3. Run `python scripts/setup_gmail_auth.py` and complete Google sign-in. This creates `token.json` (never commit it).
4. Add your job-alert preferences to your local `config.yaml`.
5. Optionally set `GEMINI_API_KEY` in your local `.env` and add your resume under `resume/`.

The files `.env`, `credentials.json`, `token.json`, local databases, logs and resume files are ignored by Git.

## GitHub Actions

The workflow is **manual only** while this repository is public. It does not write job history to a public Git branch or Actions cache.

To run it, add the required values under **Settings → Secrets and variables → Actions**:
- `GMAIL_TOKEN_JSON`: full contents of your local `token.json`
- `GEMINI_API_KEY`: optional Gemini API key
- `RESUME_TEXT`: optional resume text

Then select **Actions → Manual job scan → Run workflow**.

**Important limitation:** each hosted run uses a temporary database. Job history and tracker changes do not persist between runs. Do not enable scheduled runs until a private persistent database has been configured. Never store job history in a branch of this public repository.

## Tests

```bash
python -m pytest
```

## Project structure

```
app/                    Core pipeline, Gmail client, parsers, filters, matcher and tracker
dashboard.py            Streamlit dashboard
tests/                  Automated tests
scripts/                Gmail authentication and local scheduler helpers
.github/workflows/      Manual GitHub Actions workflow
config.yaml             Public-safe defaults only
```

## Known limitations

- Email formats can change, which may require parser updates.
- Some job sites block automated page checks; blocked pages are reported as unverifiable rather than assumed expired.
- Gmail OAuth credentials can expire or require renewed consent.
- Streamlit Community Cloud has an ephemeral local filesystem. A production deployment needs a secure OAuth flow and persistent private storage before personal Gmail/job data is used.
- Respect the terms of service of job platforms when using page verification.
