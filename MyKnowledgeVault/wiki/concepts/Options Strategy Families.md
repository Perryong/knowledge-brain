---
address: c-000013
type: concept
title: Options Strategy Families
status: developing
created: 2026-08-26
updated: 2026-08-26
tags:
  - concept
  - trading
  - options
---

# Options Strategy Families

The ~30 strategies in the [[Tastylive Options Strategy Guide]], grouped by
directional assumption and risk type. Every page in the guide follows one
template: setup, IV environment, ~45 DTE, probability of profit, max
profit/loss/breakeven formulas, profit target, defensive tactics.

| View | Undefined risk | Defined risk |
|---|---|---|
| Bullish | covered call, big lizard | long call vertical, call ZEBRA, poor man's covered call, call calendar, call butterfly |
| Neutral-bullish | short naked put | short put vertical, jade lizard |
| Neutral | short strangle, short straddle | iron condor, dynamic-width iron condor, iron fly |
| Neutral-bearish | short naked call | short call vertical, reverse jade lizard |
| Bearish | covered put | long put vertical, put ZEBRA, poor man's covered put, put calendar, put butterfly |
| Omnidirectional | front-ratio spreads | broken-wing and broken-heart butterflies |

Key formulas (verified against a live chain — see
[[Options Income and Orderflow Research]]):

- Short put: max profit = credit; breakeven = strike − credit;
  max loss = strike×100 − credit.
- Vertical spread: max profit = width − debit (or credit); risk capped.
- Iron condor: max profit = credit; max loss = widest spread − credit;
  breakevens = short strikes ∓ credit.
- Probability of profit 60–80% for the credit strategies; profit target 50%
  of max (25% for straddles/flies).

Related: [[Options Premium Selling]].

See the [[index|Wiki Index]].
