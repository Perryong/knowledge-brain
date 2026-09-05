---
address: c-000015
type: concept
title: Order Book and Liquidations
status: developing
created: 2026-08-26
updated: 2026-08-26
tags:
  - concept
  - trading
  - order-flow
---

# Order Book and Liquidations

From the [[CryptoSoulz Orderflow Guide]] (pp.8–14, 18–20). Real-time tools;
neither has a historical data feed, so neither is backtestable here.

## Order book

Resting limit orders on both sides: bids below, asks above. Narrow spread and
deep book = liquidity; **walls** (large clusters) act as visible
support/resistance that can vanish in seconds; **liquidity gaps** let price
jump. Bullish read: buy walls under price holding, sell walls being absorbed.
Bearish read: the mirror image.

## Liquidation heatmap

Marks where leveraged positions get force-closed. Clusters of short
liquidations above price can fuel squeezes; long-liquidation clusters below
can cascade. The guide treats both as magnets price seeks out.

## Evidence status

**Unsupported** — the claims are illustrated, not measured, and no historical
depth/liquidation data exists to test them
([[Options Income and Orderflow Research]]). Rule 5 of the
[[Investment Entry Checklist]] (volume ratio, wicks) is this vault's
bar-based stand-in for "buyers in control". Related:
[[Candle and Volume Confirmation]].

See the [[index|Wiki Index]].
