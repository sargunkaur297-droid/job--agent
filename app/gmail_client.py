"""Gmail API access: read job-alert emails and send the digest (OAuth, no passwords)."""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import ROOT
from .models import EmailMessage

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
CREDENTIALS_FILE = ROOT / "credentials.json"
TOKEN_FILE = ROOT / "token.json"


class GmailAuthError(RuntimeError):
    """Gmail login is missing or expired (typical: OAuth app still in 'Testing' => token dies after 7 days)."""


GMAIL_FIX = ("Gmail login expired or missing. Fix: run `python scripts/setup_gmail_auth.py` again, then update the "
             "GMAIL_TOKEN_JSON secret on GitHub with the new token.json. To stop this recurring, publish the OAuth app "
             "(Google Cloud Console -> OAuth consent screen -> Publish app).")


def run_oauth_flow() -> None:
    """One-time browser login. Creates token.json."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"{CREDENTIALS_FILE} not found. Download the OAuth 'Desktop app' client file "
            "from Google Cloud Console and save it there (see README step 3).")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json())


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    env = os.getenv("GMAIL_TOKEN_JSON")
    if env:
        creds = Credentials.from_authorized_user_info(json.loads(env), SCOPES)
    elif TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds and not creds.valid and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:                       # google.auth.exceptions.RefreshError (invalid_grant / expired)
            raise GmailAuthError(f"{GMAIL_FIX} ({str(e)[:120]})") from e
        if not env:
            TOKEN_FILE.write_text(creds.to_json())
    if not creds or not creds.valid:
        raise GmailAuthError(GMAIL_FIX)
    return creds


def get_service():
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _walk(part, out):
    mime = part.get("mimeType", "")
    data = (part.get("body") or {}).get("data")
    if data and mime in ("text/html", "text/plain"):
        out.setdefault(mime, []).append(_decode(data))
    for sub in part.get("parts") or []:
        _walk(sub, out)


def message_from_api(raw: dict) -> EmailMessage:
    headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
    bodies: dict = {}
    _walk(raw.get("payload", {}), bodies)
    ts = int(raw.get("internalDate", "0")) / 1000
    return EmailMessage(
        id=raw["id"], sender=headers.get("from", ""), subject=headers.get("subject", ""),
        date=dt.datetime.fromtimestamp(ts, dt.timezone.utc),
        html="\n".join(bodies.get("text/html", [])), text="\n".join(bodies.get("text/plain", [])))


def fetch_messages(service, query: str, max_results: int = 60, skip_ids=()) -> list[EmailMessage]:
    ids, token = [], None
    while len(ids) < max_results:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=min(100, max_results), pageToken=token).execute()
        ids += [m["id"] for m in resp.get("messages", [])]
        token = resp.get("nextPageToken")
        if not token:
            break
    out = []
    for mid in ids[:max_results]:
        if mid in skip_ids:
            continue
        raw = service.users().messages().get(userId="me", id=mid, format="full").execute()
        out.append(message_from_api(raw))
    return out


def own_address(service) -> str:
    return service.users().getProfile(userId="me").execute()["emailAddress"]


def send_email(service, to: str, subject: str, html: str) -> None:
    to = to or own_address(service)
    msg = MIMEMultipart("alternative")
    msg["To"], msg["Subject"] = to, subject
    msg.attach(MIMEText("Open this email in an HTML-capable client.", "plain"))
    msg.attach(MIMEText(html, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
