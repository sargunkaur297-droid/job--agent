# Job Agent

A personal job-search assistant that turns job-alert emails into a shortlist you can actually work through. It reads alerts from Indeed, LinkedIn and Naukri via Gmail, extracts and merges listings, checks posting links where possible, applies your search criteria, and keeps an application tracker in one place.

The goal is to reduce repetitive screening — not to apply on your behalf. You stay in control of every application.

## What it does

- **Collects job alerts** from Gmail using OAuth.
- **Extracts and normalises listings** from Indeed, LinkedIn and Naukri email formats.
- **Merges duplicates** so the same role received from multiple sources is easier to manage.
- **Checks job links** for posting dates, expired listings and pages that cannot be verified.
- **Filters opportunities** by role, location, seniority, experience and posting age.
- **Ranks relevance** with a local matching method or optional Gemini scoring, with reasons and gaps.
- **Tracks applications** with status, date and notes in a Streamlit dashboard.
- **Sends a digest** of relevant opportunities by email.

Some job sites restrict automated page checks. A blocked page is marked as *unverifiable* rather than being treated as expired.

## Project at a glance

| Area | Tools |
| --- | --- |
| Language | Python |
| Dashboard | Streamlit |
| Data | SQLite |
| Email access | Gmail API, OAuth 2.0 |
| Parsing | Beautiful Soup |
| Optional matching | Google Gemini |
| Tests | pytest |
| Automation | GitHub Actions (manual workflow) |

## Getting started

### Requirements

- Python 3.11 or newer
- A Gmail account with job-alert emails from supported platforms
- Google Cloud OAuth credentials for Gmail access
- A Gemini API key only if you want AI-based scoring

### Install

```bash
git clone https://github.com/sargunkaur297-droid/job--agent.git
cd job--agent

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Create a local environment file:

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

Add your optional `GEMINI_API_KEY` to `.env`. The local matcher works without it.

### Connect Gmail

1. Enable the Gmail API in Google Cloud Console.
2. Create an OAuth client of type **Desktop app**.
3. Download the client file and save it in the project root as `credentials.json`.
4. Run the authentication helper:

   ```bash
   python scripts/setup_gmail_auth.py
   ```

5. Complete Google's sign-in flow. The helper saves `token.json` locally.

The OAuth files are local credentials. Do not commit or share them.

### Configure your search

Edit your local `config.yaml` with the roles, locations, skills and filters you want to use. The version committed to this public repository contains only generic defaults.

Optionally add a PDF, DOCX or text resume under `resume/` for matching. Resume files and local databases are excluded from Git.

### Run

Start the dashboard:

```bash
streamlit run dashboard.py
```

Or run the pipeline from a terminal:

```bash
python -m app.run_daily
```

To try the pipeline with sample data without connecting Gmail:

```bash
python -m app.run_daily --demo
```

## Tests

Run the automated test suite:

```bash
python -m pytest
```

The tests cover parsing, normalisation, filtering, date handling, duplicate handling, pipeline behaviour, matching and application tracking. They do not replace a live check with your own Gmail account or external job sites.

## Repository layout

```text
app/                    Core pipeline and supporting modules
app/parsers/            Platform-specific email parsers
dashboard.py            Streamlit dashboard
config.yaml             Generic, public-safe defaults
data/                   Local database and runtime files (ignored)
resume/                 Local resume files (ignored)
sample_emails/          Sanitised sample alert emails
scripts/                Gmail setup and local run helpers
tests/                  Automated tests
docs/                   Architecture and project notes
.github/workflows/      Manual GitHub Actions workflow
```

For more detail, see [the architecture notes](docs/ARCHITECTURE.md) and [the project report](docs/PROJECT_REPORT.md).

## GitHub Actions

The included workflow is manual-only. It can run the pipeline with repository Actions secrets, but its database is temporary and does not preserve job history between runs.

To use it, add the required values under **Settings → Secrets and variables → Actions**:

- `GMAIL_TOKEN_JSON`: contents of your local `token.json`
- `GEMINI_API_KEY`: optional Gemini API key
- `RESUME_TEXT`: optional resume text

Then open **Actions → Manual job scan → Run workflow**.

Do not enable scheduled runs or store job history in a branch or Actions cache of this public repository. A persistent private database is needed before using hosted runs as an ongoing personal tracker.

## Privacy

This is a public repository. Keep personal information and credentials out of commits.

The repository ignores local environment files, OAuth credentials, databases, logs and resume files. Before pushing changes, check that you are not adding any of the following:

- `.env`, `credentials.json` or `token.json`
- Personal resumes or exported job/application data
- Local SQLite databases, logs or debug output
- A personalised `config.yaml`

If a secret has ever been committed, removing it from the latest version is not enough. Rotate the exposed credential and clean the Git history.

## Current limitations

- Email templates can change, so individual parsers may need maintenance.
- Job sites may block automated verification or require a sign-in.
- Gemini scoring is optional; the local matcher is available as a fallback.
- The dashboard currently uses a local SQLite database. Streamlit Community Cloud's local filesystem is not suitable for durable personal records.
- The Gmail setup described above uses a desktop OAuth flow. A hosted deployment needs a web-compatible OAuth flow and secure persistent storage before it should handle personal Gmail or job-search data.

