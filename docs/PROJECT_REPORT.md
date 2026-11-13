# Project Report: Job Agent

## Problem

Job alerts arrive from multiple platforms and often repeat the same opportunity. They can also include roles that are too senior, outside the preferred location, no longer open or unrelated to a candidate's skills. Reviewing each message manually takes time.

## Objective

Build a personal assistant that collects supported job alerts, organises listings, applies configurable search criteria and helps the user keep track of applications. The user remains responsible for reviewing each role and submitting applications.

## Approach

1. **Ingestion** — Gmail API access retrieves alert emails from supported sources.
2. **Parsing** — Platform-specific parsers extract job titles, companies, locations, descriptions, links and posting-time hints.
3. **Normalisation** — Titles, company names and URLs are standardised to help identify duplicate listings.
4. **Verification** — Public job pages are checked for posting dates and expiry signals where access is available. Blocked pages are treated as unverifiable.
5. **Filtering** — Configurable rules check posting age, target roles, locations, seniority and experience.
6. **Relevance scoring** — A local matcher provides a baseline score. Optional Gemini scoring adds a second relevance estimate with reasons and gaps.
7. **Tracking and review** — A Streamlit dashboard presents jobs and lets the user maintain application statuses, dates and notes.
8. **Notifications** — Relevant opportunities can be sent in an email digest.

## Technology

Python, SQLite, Streamlit, pandas, Beautiful Soup, Requests, Gmail API with OAuth 2.0, Google GenAI SDK and pytest.

## Testing

The automated test suite covers core parsing and filtering behaviour, date handling, normalisation, duplicate processing, pipeline behaviour and application tracking. External Gmail, Gemini and live job-site behaviour depend on account access and network responses, so they need separate manual verification.

Run the tests with:

```bash
python -m pytest
```

## Limitations

- Email layouts may change and require parser updates.
- Job sites can block automated requests or require authentication, limiting page verification.
- Gemini scoring requires an API key; the local matcher is the fallback.
- The current dashboard uses a local SQLite database. A hosted deployment needs private persistent storage to retain personal job and application data.
- The Gmail authentication helper uses a desktop OAuth flow. Hosted use requires a web-compatible OAuth implementation.

## Next steps

- Add integration tests using controlled Gmail and job-page fixtures.
- Improve observability for failed parsing and verification attempts.
- Introduce a secure web OAuth flow and persistent private storage before offering a hosted version.
- Add additional alert formats based on real sample emails.

