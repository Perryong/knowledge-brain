---
address: c-000004
type: concept
title: Moving Averages
status: evergreen
created: 2026-08-23
updated: 2026-08-24
tags:
  - concept
  - trading
  - technical-analysis
---

# Moving Averages

From [[Investment Guide Notes]] (page 3). Background for rule 3 of the
[[Investment Entry Checklist]], which since 2026-08-24 uses the EMA12/EMA21
pair below; the MA10/MA30/MA50/MA200 material stays as context. Core idea: **look at the slope** — MA lags, and
the longer the MA, the slower it reacts. Use the daily chart (1M view); for
long-term decisions confirm on the 1Y chart.

## EMA12 / EMA21 swing trend (rule 3 since 2026-08-24)

- **Trend up:** EMA12 above EMA21. **Entry:** price pulls back to EMA21 and
  closes at or above it (within ~3% is the textbook entry; a continuation buy
  further above still qualifies once rules 4–5 confirm).
- **Exit:** EMA12 closes back below EMA21 — this is the stop, not MA30.
- A close below EMA21 while EMA12 is still above it is "pullback not yet
  bought": wait for the reclaim, do not catch it.
- Why EMA over the MA200 zones: see the backtest note on the
  [[Investment Entry Checklist]] page.

## Pre-buy checklist (short-term)

All true → good short-term entry:

- MA10 > MA30
- MA30 sloping upward
- Price pulled back near MA10 (small wick / small red candle = temporary
  pause, not a trend break)
- Price still above MA30
- Long lower wicks

## Situations

| Situation | MA to watch | Action |
|---|---|---|
| Short-term entry | MA10 / MA30 | Buy pullback to MA10 above MA30 |
| Short-term exit | MA30 | Exit on close below |
| Long-term entry | MA50 / MA200 | Buy pullback to MA50 |
| Long-term hold | MA200 | Hold above |
| Long-term exit | MA200 (weekly) | Exit below |

**Exit / warning rules:** MA10 drops below MA30 = warning, not an emergency —
stop adding, hold, watch price vs MA30. Daily close below MA30 = exit the
short-term trade (this is the line in the sand). MA30 sloping down = trend
failure — exit and no re-entry until structure repairs. Conservative exit:
daily close below MA30 (especially if MA10 < MA30). Aggressive exit: MA10
crosses below MA30, momentum clearly dies. Why this works: losses cut early,
winners run, no falling knives.

## Distance from MA200 (long-term)

- **0–20% above** — safe to enter on MA50 pullbacks; normal position size.
- **20–40% above** — still bullish; do **not** add; hold if already in.
- **40–60% above** — take partial profits; tighten stops (MA30/MA50); expect
  sharp pullbacks.
- **>60% above** — distribution territory; new entries = gambling; only hold a
  reduced position.

When price is far above MA200: **wait, always.** Good long-term entries come
from a pullback to MA50, long consolidation while MA200 catches up, or
multi-month bases. Buying extended means risk 3–5× larger with limited
short-term upside.

## Distance from MA30 (short-term)

0–5% above = safe zone (comfortable to buy/add); 5–10% = caution zone (buy
only on pullbacks to MA10/MA20); >10–12% = risky/stretched.

## Double bottom (W)

Suggests sellers tried twice and failed, buyers are absorbing supply, momentum
may be shifting up — but **W is NOT bullish until confirmed**: price breaks
above the middle peak (the "neckline"), holds above MA30, MA10 > MA30, and
volume expands.

See the [[index|Wiki Index]].
