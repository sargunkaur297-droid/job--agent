"""One-time Gmail login. Run:  python scripts/setup_gmail_auth.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.gmail_client import TOKEN_FILE, get_service, own_address, run_oauth_flow  # noqa: E402

if __name__ == "__main__":
    run_oauth_flow()
    print(f"Saved {TOKEN_FILE}")
    print("Connected as:", own_address(get_service()))
    print("For GitHub Actions: copy the full contents of token.json into the GMAIL_TOKEN_JSON secret.")
