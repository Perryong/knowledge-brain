---
type: meta
title: Hot Cache
status: developing
created: 2026-08-23
updated: 2026-08-24
tags:
  - meta
  - hot-cache
---

# Recent Context

## Last Updated

2026-08-24 — entry checklist rule 3 switched to EMA12/EMA21 after backtests.

## Key Recent Facts

- [[commands|Claude-Obsidian Command Reference]] documents all 15 skills, their trigger
  phrases, and the portable CLI for this vault (product v2.1.0).
- The vault's first source is [[Investment Guide Notes]]: a personal 5-point
  stock entry framework (business quality, Forward ≤ TTM P/E, trend +
  pullback, VWAP, candle+volume confirmation).
- **Rule 3 is now EMA12 > EMA21 with an EMA21-pullback entry and EMA
  cross-down exit** (2026-08-24). Backtested 2016–2026 on NVDA, BTC, TSLA,
  ARM, NBIS, VOO, gold: best Sharpe of eight strategies on every instrument;
  the old MA200 zone rule sat out most of NVDA's decade. Details on
  [[Investment Entry Checklist]].
- Institutional involvement threshold used throughout: volume ratio > 1.5 and
  turnover > 1% near support/VWAP/MA.

- Latest [[NVDA 2026-08-23|NVDA check]] (data 2026-08-21 close): valuation
  and trend rules pass; entry blocked by rule 4 (below VWAP) and rule 5
  (volume ratio 0.84, no buyer confirmation). Watch for a VWAP/MA10 reclaim
  on expanding green volume; setup fails on a daily close below MA30 211.33.

- [[AAOI 2026-08-23|AAOI check]] (data 2026-08-21): WAIT — loss-making
  (EPS -0.77, rule 2 unscorable), 28% above MA200 in the no-add zone, below
  MA10/MA50 and VWAP, VR 0.74. After-hours fell a further -10% past the
  scored session. Rule 1 awaits the holder's own business judgement.

## Recent Changes

- Created [[commands|Claude-Obsidian Command Reference]] (operation
  `autoresearch-skill-reference-20260823`).
- Created 1 source page and 5 concept pages from the investment-guide ingest
  (operation `ingest-investment-guide-20260823`).

## Active Threads

- Vibe-Trading MCP server installed (user scope); `trade-check` now drives
  it (`bt_prepare.py` / `bt_report.py`, 8 strategies, daily or 1H). Backtest
  artifacts live in `~/.vibe-trading/runs/`, not in the vault.

- New custom skill `/claude-obsidian:trade-check` evaluates a ticker against
  [[Investment Entry Checklist]] and files dated scorecards in
  `wiki/trade-checks/`.

- Trading-note claims are recorded as provisional (single primary source);
  candidates for a future web autoresearch pass with egress consent.
