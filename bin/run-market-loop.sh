#!/usr/bin/env bash
# One market cycle: fetch -> analyze -> render -> commit.
# The D2 script-driven auto-commit lives here (not a plugin hook).
#
#   TWELVEDATA_API_KEY=... bash bin/run-market-loop.sh
#
# Re-running the same day re-fetches fresh prices and overwrites that day's pages
# (history rows stay keyed by date, so no duplication). Free tier is 8 req/min, so
# don't run twice inside a minute. Exits non-zero if any stage fails (scheduler can alert).
set -euo pipefail

VAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$VAULT"

# Resolve a WORKING Python 3. Never probe with `command -v python3`: on Windows
# that name is a Microsoft Store stub which is present on PATH but exits 49 when
# run. See scripts/python-bin.sh.
PY="$(bash "${VAULT}/scripts/python-bin.sh" 2>/dev/null || true)"
if [ -z "$PY" ]; then
  echo "ERROR: no working Python 3 found (tried python3, python, py -3)." >&2
  echo "       If 'python3' prints \"Python was not found\", disable the Microsoft" >&2
  echo "       Store alias: Settings > Apps > Advanced app settings >" >&2
  echo "       App execution aliases > turn off python3.exe" >&2
  exit 1
fi


: "${TWELVEDATA_API_KEY:?set TWELVEDATA_API_KEY in the environment (never in a tracked file)}"

echo "[$(date '+%F %T')] fetch"   && $PY scripts/fetch-market.py
echo "[$(date '+%F %T')] analyze" && $PY scripts/analyze-market.py
echo "[$(date '+%F %T')] render"  && $PY scripts/render-market.py

if [ -d .git ]; then
  git add -- wiki/ .raw/market-data/
  if git diff --cached --quiet; then
    echo "[$(date '+%F %T')] no changes to commit"
  else
    git -c user.name="market-loop" -c user.email="noreply@anthropic.com" \
        commit -q -m "market: auto-commit $(date '+%F %H:%M')"
    echo "[$(date '+%F %T')] committed $(git rev-parse --short HEAD)"
  fi
  # Push any unpushed commits. Non-fatal: a network/credential failure must not
  # break the local commit (osxkeychain + gh supply creds in a real shell; cron
  # has network, the Claude sandbox does not). First push must be done by hand.
  if git remote get-url origin >/dev/null 2>&1; then
    if git push -q origin main; then
      echo "[$(date '+%F %T')] pushed to origin/main"
    else
      echo "[$(date '+%F %T')] push failed (non-fatal) — will retry next run"
    fi
  fi
else
  echo "[$(date '+%F %T')] no .git — skipped commit"
fi
