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

: "${TWELVEDATA_API_KEY:?set TWELVEDATA_API_KEY in the environment (never in a tracked file)}"

echo "[$(date '+%F %T')] fetch"   && python3 scripts/fetch-market.py
echo "[$(date '+%F %T')] analyze" && python3 scripts/analyze-market.py
echo "[$(date '+%F %T')] render"  && python3 scripts/render-market.py

if [ -d .git ]; then
  git add -- wiki/ .raw/market-data/
  if git diff --cached --quiet; then
    echo "[$(date '+%F %T')] no changes to commit"
  else
    git -c user.name="market-loop" -c user.email="noreply@anthropic.com" \
        commit -q -m "market: auto-commit $(date '+%F %H:%M')"
    echo "[$(date '+%F %T')] committed $(git rev-parse --short HEAD)"
  fi
else
  echo "[$(date '+%F %T')] no .git — skipped commit"
fi
