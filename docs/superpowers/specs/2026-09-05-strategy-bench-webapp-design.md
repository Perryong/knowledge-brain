# Strategy Bench web app — design

Date: 2026-09-05 · Status: approved in chat, pending spec review
Decisions locked during brainstorming: GitHub Actions + Pages (option C);
`knowledge-brain` becomes **public** and Pages serves from `docs/` (option B,
chosen with the vault-exposure warning acknowledged); new-signal alerts via a
GitHub issue per scan day (option B).

## Purpose

Bring the Strategy Bench dashboard into this repo and add a **nightly signal
scan**: run every backtested strategy over a watchlist on fresh daily bars,
publish the dashboard to GitHub Pages, and open a GitHub issue when a strategy
flips to BUY or SELL.

## Layout

```
webapp/
├── strategies.py        # single source of truth: REGISTRY = {name: {generate, buy, sell, gated, cap}}
│                        #   14 engines extracted from skills/trade-check/scripts/bt_prepare.py's
│                        #   template plus the smcstruct/ewabc pandas engines. Pure pandas/numpy.
├── watchlist.json       # [{"name","source","code"}] — initial: NVDA, XAUUSD (GC=F/yfinance),
│                        #   BTCUSDT (OKX), ARM, NBIS, VOO, TSLA
├── backtests.json       # historical metrics grid baked once from ~/.vibe-trading/runs.
│                        #   The scan never re-runs backtests.
├── scan.py              # entry point: fetch → run engines → docs/data.json + docs/index.html
│                        #   + signals summary on stdout / --github-output for the Action
└── selfcheck.py         # offline: every engine parses and produces expected states on a
│                        #   bundled synthetic fixture; page builder renders headlessly
docs/                    # GitHub Pages root; index.html + data.json are build artifacts
│                        #   committed by the Action (and by local runs)
.github/workflows/scan.yml
```

`skills/trade-check` keeps its own engine template; no refactor of it here.

## Scan semantics

Per ticker × strategy:

- Fetch ~2 years of daily bars (yfinance for equities/gold `GC=F`; OKX public
  candles for `BTC-USDT`). No API keys.
- Replay the engine over the full history (engines are stateful; replay yields
  the true current state). No lookahead: same confirmed-pivot/window logic as
  the backtests.
- Emit: `state` (holding | flat), `action` (BUY | SELL | none — state flip on
  the latest bar), and for `ema`/`smcstruct`/`ewabc` a `trigger` distance
  (gap to EMA cross / last swing high / last swing low).
- A failed fetch marks the ticker `stale` (page shows the badge and the last
  good date); the scan continues. The job fails only if every fetch fails.

## Page (docs/index.html)

The existing Strategy Bench (equity curves, candlestick chart with
strategy-generated levels and fills, per-ticker table, Sharpe heatmap, trade
log, Pine export) plus:

- **Today's signals** panel first: fresh BUY/SELL highlighted; full
  state matrix (ticker × strategy) with holding/flat and trigger distances.
- **Strategy rules** table: buy condition · sell condition · gating note for
  all 14 strategies (from `strategies.py`, so page text and code cannot drift).
- Candles/fills refresh each scan; equity + metrics panels remain historical
  from `backtests.json`.

## Action (.github/workflows/scan.yml)

- Triggers: cron `30 22 * * 1-5` (after US close) + `workflow_dispatch`.
- Steps: checkout → setup-python → `pip install pandas numpy yfinance requests`
  → `python webapp/selfcheck.py` (abort on failure) → `python webapp/scan.py`
  → commit `docs/` if changed → if the scan reports new signals, create one
  issue titled `Signals YYYY-MM-DD: NVDA·ema BUY, …`, label `signal`, via the
  built-in `GITHUB_TOKEN` (permissions: `contents: write`, `issues: write`).
  GitHub notifications deliver the email.
- Known risk: Yahoo rate-limiting from CI runners — mitigated by retry with
  backoff and the per-ticker `stale` path; a failed run leaves yesterday's
  page in place.

## Running it

- Cloud: automatic nightly; or Actions → *Scan* → Run workflow.
- Local: `python webapp/scan.py` then open `docs/index.html`. Same code path;
  no server.

## Testing

`selfcheck.py` is the gate: engine registry imports, synthetic-fixture replay
produces the expected state/action for at least one BUY and one SELL case per
engine family, and the page builder renders with all panels populated
(headless DOM-less check). CI runs it before every publish; it also runs
locally before committing changes to `webapp/`.

## Out of scope

Nightly backtest re-runs in CI; intraday scanning; broker/order integration;
republishing the Claude artifact from CI (the Pages URL becomes canonical);
any refactor of `skills/trade-check`.

## Acknowledged consequence

Making the repo public exposes the vault (personal notes, trade verdicts) and
`.raw` captures including two commercial PDF guides (copyright risk in
redistribution), plus full git history. Amendment available on request:
relocate the vault to a private repo (or `.gitignore` it forward) before the
repo is flipped public — this spec does not include that work.
