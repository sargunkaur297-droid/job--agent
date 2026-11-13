# Job Agent

Reads your **Indeed, LinkedIn and Naukri job-alert emails** from Gmail, removes duplicates, checks each
posting is genuinely **new (≤ 24 h), open and in your cities**, and emails you **every single listing that follows your rules** (no score cut-off) every morning at 9:00,
plus a **Streamlit dashboard** and application tracker.

> **It never applies for you.** You open the link, apply yourself, then mark it *Applied* in the tracker.

```
Indeed / LinkedIn / Naukri alert emails
        │  Gmail API (read-only + send)
        ▼
 Parse → normalise → de-duplicate  ──►  SQLite (data/jobs.db)
        ▼
 Verify (open page: real posting date, expired/404)  →  Filter (24h, city, role, level, experience)
        ▼
 Every matching job → Application tracker  (AI score is optional and only used for sorting)
        ▼
 Streamlit dashboard  +  daily digest email  (GitHub Actions or local scheduler)
```

## 1. Install

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

## 2. Try it now, no accounts needed

```bash
python -m app.run_daily --demo     # loads sample Indeed/LinkedIn/Naukri emails
streamlit run dashboard.py
python -m pytest                   # 43 tests
```

## 3. Connect Gmail (one time, ~5 minutes)

1. Go to <https://console.cloud.google.com/> → create a project (any name).
2. **APIs & Services → Library** → enable **Gmail API**.
3. **OAuth consent screen** → *External* → fill app name + your email → add yourself under **Test users**.
4. **Credentials → Create credentials → OAuth client ID → Desktop app** → **Download JSON**.
5. Save it in this folder as `credentials.json`.
6. Run `python scripts/setup_gmail_auth.py`. A browser opens; approve. This creates `token.json`.

   (Google may warn "app not verified" because it is your own app in test mode: *Advanced → Continue*.)
   Tokens of apps left in *Testing* expire after 7 days. To avoid that, on the consent screen click **Publish app**
   (for personal use no review is needed for your own account).

**Make sure alerts exist:** create job alerts on Indeed, LinkedIn and Naukri using the same Gmail address,
set to daily or instant.

## 4. (Optional) Gemini key and resume

Not needed for the emails any more: **no job is ever dropped because of a score**. Only if you set
`matching.enabled: true` in `config.yaml` are jobs also given a match score, used purely for sorting in the dashboard.

1. Free key: <https://aistudio.google.com/apikey> → put it in `.env` as `GEMINI_API_KEY=...`.
2. Put your resume (`.pdf`, `.docx` or `.txt`) in the `resume/` folder.
3. Edit `config.yaml`: your name, graduation year, `target_roles`, `skills`, `notes`, cities.

Without a key or resume the app still works using the local keyword matcher (less detailed explanations).

## 5. Run

```bash
python -m app.run_daily            # ingest → verify → filter → match → email digest
streamlit run dashboard.py         # review, update tracker
```

Options: `--no-notify` (don't email), `--no-verify` (don't open job pages), `--demo`.

## 6. Automate daily

**GitHub Actions (runs even when your PC is off)**
1. Create a **private** GitHub repo and push this folder (`.env`, `token.json`, `credentials.json` and your
   resume are git-ignored).
2. Repo → *Settings → Secrets and variables → Actions* → add:
   - `GMAIL_TOKEN_JSON` – paste the full contents of `token.json`
   - `GEMINI_API_KEY`
   - `RESUME_TEXT` – paste your resume as plain text
3. *Actions → Daily job scan → Run workflow* to test. It then runs daily at 09:00 IST
   (edit the cron in `.github/workflows/daily.yml`).

The database persists between runs through the Actions cache, so duplicates are never re-emailed.
Note: the dashboard reads the local DB, so use it on the machine where you run the pipeline. In the
Actions mode you mostly use the email digest.
If the cache is ever evicted (unused for 7 days) the DB restarts empty; old jobs may be re-sent once.

**Local scheduler (Windows, one command)**
Run the scan every day shortly AFTER your job-alert emails arrive (e.g. alerts at 8:00 → scan at 9:00):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\schedule_windows.ps1 -Time 09:00
Start-ScheduledTask -TaskName JobAgentDaily      # test it right now
```
Check `data\run.log` for the result and your Gmail for the digest. Run the first command again with a different
`-Time` to change it; `scripts\unschedule_windows.ps1` removes it. Your PC must be on (or it runs when it next wakes).
- Manual alternative: Task Scheduler → Create Basic Task → Daily → Start a program → `scripts\run_daily.bat`
- macOS/Linux: `crontab -e` → `30 9 * * * /full/path/job_agent/scripts/run_daily.sh`

Logs go to `data/run.log`. You can run it several times a day: only jobs not yet emailed are included.

## What the email contains

* **Every job** that passed your rules (cities, roles, level, experience) and was posted in the **last 24 h**
  from LinkedIn, Naukri and Indeed, newest first. No score cut-off, no "top 15" limit.
* Per job: **role (click to open the job directly)**, company, **location**, source, age, link status.
* One email holds up to **150 jobs** (`notifications.jobs_per_email`); bigger lists are split automatically
  into "(1/2)", "(2/2)"... so Gmail never clips them. 100+ jobs in one email works.
* You get an email **every run**, even with 0 jobs (it tells you so). `notifications.mode: last_24h` (default)
  re-lists the whole last-24h set on each run; `new_only` lists only jobs not emailed before.
* Link status: ✓ = page opened fine; **?** = LinkedIn/Indeed blocked the automatic check (open to confirm).
  Expired / 404 / "no longer accepting" jobs are removed automatically and never emailed.
* Daily at **9:00 AM IST**: GitHub Actions cron `30 3 * * *` (UTC) or the Windows task. GitHub may start
  scheduled runs a few minutes late. Your job alerts must arrive **before** 9:00 (set them to daily/instant).

## Safety nets (so a quiet failure never goes unnoticed)

* **Gmail login expired** (the usual reason the daily email stops): the run stops with a clear message and a
  failing status. On GitHub it also **opens an issue "Job Agent run failed"**, which emails you. Fix: run
  `python scripts/setup_gmail_auth.py`, update the `GMAIL_TOKEN_JSON` secret. To stop it recurring, publish your
  OAuth app (Google Cloud Console → OAuth consent screen → **Publish app**); apps left in *Testing* expire every 7 days.
* **Broken parser / dead alert:** the email shows a yellow "Check this" box if a platform sent no alert emails in the
  last 2 days, or emails were read but 0 jobs were found (layout probably changed).
* **"Filtered out by your rules"** section at the end of the email lists what was dropped and why (top reasons +
  up to 60 jobs). Loosen a rule in `config.yaml` if something there looks right. Turn off with
  `notifications.show_filtered_out: false`.
* **Better link checking:** blocked pages are retried once, LinkedIn's public logged-out page is tried as a fallback,
  and when a job has several links the one that actually opened becomes the one in your email.
* **Database never expires on GitHub:** after every run `jobs.db` is saved to a one-commit branch called
  `job-data` (plus the Actions cache as a backup). It is restored at the start of each run. Keep the repo
  **private**: that branch contains your job list. Needs *Settings → Actions → General → Workflow permissions →
  Read and write* only if your account/org restricts it (the workflow already requests `contents: write`).

## How filtering works

| Check | Rule |
|---|---|
| Posting date | Page `datePosted` (✅ verified) → email "2 hours ago" hint → email date. `date_policy` in `config.yaml` decides which are trusted. Default `allow_unverified` (so jobs from alert emails are not lost; those show `~` in the email). Anything older than `max_age_hours` (24) is rejected. |
| Expired / broken | HTTP 404/410, "no longer accepting applications", `validThrough` in the past → rejected. |
| Blocked pages | LinkedIn/Indeed often block bots (403/429). Those are marked *unverifiable*, not rejected. |
| Location | Must be one of your cities (aliases handled: Bangalore → Bengaluru, Gurgaon → Gurugram). Unknown location: `keep` or `reject`. |
| Role | Title or description must contain a `target_roles` phrase; title must not contain `avoid_title_keywords`. |
| Experience | Rejects explicit requirements above `max_experience_years`. `require_level_signal: true` also demands intern/fresher wording. |
| Duplicates | Same company + similar title + same city across platforms merge into one job with all apply links. |

Every rejected job keeps its reason (dashboard → Overview → "Why jobs were rejected"), so you can tune the rules.

## Tracker statuses

Shortlisted · Not applied · Applied · Interview scheduled · Rejected · Offer received.
Application date, link and notes are saved; status changes are logged with dates.

## Project layout

```
app/            config, db, gmail_client, parsers/, dates, verify, filters, matcher, tracker, notify, pipeline
dashboard.py    Streamlit UI
tests/          43 pytest tests (sample emails in sample_emails/)
scripts/        Gmail auth, local scheduler helpers
.github/workflows/daily.yml
docs/           ARCHITECTURE.md, PROJECT_REPORT.md
```

## Known limits (honest notes)

- Email layouts change. If a platform changes its template, parsers may miss jobs: save the email HTML into
  `sample_emails/` and adjust `app/parsers/__init__.py`. The run output shows how many jobs each run parsed.
- Posting date accuracy depends on the source. Page-verified is best; "date from hint/email" is shown in the dashboard and digest.
- Page-level date-only values are treated as midday local time (±12 h).
- Scraping job pages may be restricted by each site's terms. The verifier makes one polite request per job
  (2 s delay); disable with `fetch_pages: false`.
- Job emails contain only snippets, so match scores use limited descriptions unless the page can be read.
