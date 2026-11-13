"""Daily entry point:  python -m app.run_daily   (use --demo to try without Gmail)."""
from __future__ import annotations

import argparse
import json
import sys

from . import db
from .config import load_config
from .matcher import LocalMatcher


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Job Agent daily run")
    ap.add_argument("--demo", action="store_true", help="use bundled sample emails, no Gmail/Gemini needed")
    ap.add_argument("--no-notify", action="store_true", help="do not send the digest email")
    ap.add_argument("--no-verify", action="store_true", help="skip opening job pages")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)

    cfg = load_config(a.config)
    if a.no_verify or a.demo:
        cfg["verification"]["fetch_pages"] = False
    from .pipeline import run_pipeline
    conn = db.connect()
    try:
        if a.demo:
            from .demo import demo_messages
            cfg["filters"]["date_policy"] = "allow_hints"
            stats = run_pipeline(conn, cfg, messages_by_source=demo_messages(), matcher=LocalMatcher(cfg),
                                 notify_email=False, sleep=False)
        else:
            from .gmail_client import GmailAuthError, get_service
            try:
                service = get_service()
            except GmailAuthError as e:
                print(f"\nERROR: {e}", file=sys.stderr)
                return 2                              # non-zero => GitHub marks the run failed and alerts you
            stats = run_pipeline(conn, cfg, service=service, notify_email=not a.no_notify)
    finally:
        pass
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
