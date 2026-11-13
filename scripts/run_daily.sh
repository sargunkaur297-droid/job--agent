#!/usr/bin/env bash
# Local scheduler helper (macOS/Linux). Add to cron:  30 9 * * *  /full/path/to/scripts/run_daily.sh
cd "$(dirname "$0")/.." || exit 1
[ -d .venv ] && source .venv/bin/activate
python -m app.run_daily >> data/run.log 2>&1
