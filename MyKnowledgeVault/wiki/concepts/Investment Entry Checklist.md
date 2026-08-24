---
address: c-000002
type: concept
title: Investment Entry Checklist
status: evergreen
created: 2026-08-23
updated: 2026-08-24
tags:
  - concept
  - trading
  - checklist
---

# Investment Entry Checklist

The master 5-point checklist from [[Investment Guide Notes]]. All five
conditions should hold before entering a position.

1. **Business makes sense.**
2. **Forward P/E ≤ TTM P/E** — earnings expected to grow, valuation improving.
   See [[Price-Earnings Ratio]].
3. **EMA12 above EMA21** (swing trend up), and buy on the **EMA21
   pullback** — close at or above EMA21, ideally within 3% of it. EMA12
   crossing back below EMA21 is the exit. See [[Moving Averages]].
   *Replaced the MA200 / MA10–MA50 rule on 2026-08-24 after backtesting; the
   MA200 distance zones remain context, not a gate.*
4. **Price above or reclaiming VWAP.** See [[VWAP]].
5. **Candle + volume confirmation** — enter only when buyers are in control.
   See [[Candle and Volume Confirmation]]:
   - *Selling pressure weakens* — red candles show shrinking volume.
   - *Buyers defend key levels* (VWAP / EMA20 / MA20 / MA30) — long lower
     wicks = rejection of lower prices.
   - *Buying pressure strengthens* — volume expands on green candles.
   - *Price acceptance* — close above VWAP or reclaim a key MA.
   - *Institutional involvement* — volume ratio > 1.5, turnover > 1%,
     price near support / VWAP / MA.

## Why rule 3 changed (2026-08-24)

Own backtests (claude-obsidian `trade-check` via the Vibe-Trading MCP, daily
bars 2016-08 → 2026-08, rules 4–5 gating every entry, 6-month hold cap):

- The MA200 rule as written kept NVDA out of the market 54% of the decade
  (its 0–20%-above-MA200 zone), with zero entries Feb 2022 → Dec 2024:
  +12% vs +13,550% buy-and-hold.
- EMA12 > EMA21 with the same rule 4–5 gate had the best Sharpe on all seven
  instruments tested (NVDA 1.05, BTC 1.12, TSLA 1.05, ARM 1.11, NBIS 1.51,
  VOO 0.88, gold 0.72), drawdowns about half of buy-and-hold, ~40% win rate,
  average hold 35–50 days — the profit comes from the ~10 holds that run
  100–200 days.
- Donchian breakout, MACD, Bollinger squeeze, and the order-flow variants
  (volume/market-profile value area, delta proxy) all ranked below it, on
  daily and on BTC 1-hour bars.

Single decade, no parameter tuning, fills at signal-bar close: treat as
evidence for the rule, not proof of returns.

See the [[index|Wiki Index]].
