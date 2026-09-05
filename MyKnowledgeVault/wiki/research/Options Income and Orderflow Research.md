---
address: c-000010
type: research
title: Options Income and Orderflow Research
status: developing
created: 2026-08-26
updated: 2026-08-26
tags:
  - research
  - trading
  - options
  - order-flow
---

# Options Income and Orderflow Research

Dossier for two user-supplied trading guides, researched without network
egress (sources: the captured PDFs, this vault, and own Vibe-Trading MCP
computations). Both are educational/promotional documents: statements below
are the guides' claims unless marked as evidence.

## Tastylive Options Strategy Guide

Doctrine ([[Tastylive Options Strategy Guide]], pp.4–5 and per-strategy pages):

1. Trade "where the stock will NOT go": sell premium for 60–80% probability
   of profit instead of a ~50/50 directional stock bet.
2. Sell when implied volatility is high; extrinsic value decays to zero.
3. Enter ~45 DTE; take profit at 50% of max (25% for straddles/flies);
   defend by rolling out in time or moving strikes, for credits.
4. Undefined-risk variants collect more premium; defined-risk variants cap
   loss at spread width − credit.

**Evidence (own computation, 2026-08-25, Vibe-Trading `get_options_chain` +
`analyze_options_payoff`, NVDA spot ≈ $212.5, ATM IV ≈ 38%, Oct-16 expiry,
53 DTE):** the guide's arithmetic checks out exactly. Short 190 put at $4.50
mid → breakeven 185.50 (= strike − credit), max profit $449.55 net, max loss
$18,550 (= strike×100 − credit). Iron condor 180/190P + 235/245C → credit
$352.59, breakevens 186.47/238.53, max loss $647.41 (= width − credit). An
IV-halving scenario at unchanged spot marks +$415 of $450 (naked put) and
+$276 of $353 (condor) — the short-vega mechanism the guide relies on.
The formulas are verified; the *performance* of the doctrine (win rates,
long-run P/L) was not tested and remains an open question.

## CryptoSoulz Orderflow Guide

Tools and bullish setups ([[CryptoSoulz Orderflow Guide]]): order-book
pressure, volume-profile POC/HVN/LVN, liquidation clusters as magnets,
market-profile value acceptance; edge claimed from combining them.

**Evidence (own backtests, 2026-08-24, daily bars 2016–2026, 7 instruments,
rules 4–5 of the [[Investment Entry Checklist]] gating every entry, 6-month
cap; artifacts `~/.vibe-trading/runs/`):** four daily-bar translations were
tested — HVN breakout (p.28), LVN rejection (p.25), rising-POC value entry
(p.23), higher-low-at-HVN (p.29). None beat the checklist's EMA12/EMA21
rule 3 on the swing horizon. Higher-low-at-HVN was best (holds 70–89 days,
positive 4/7) and is retained as an optional filter; LVN rejection behaves as
a short scalp; the rest added nothing. Order-book depth and liquidation
heatmaps have no historical feed and were not testable. A BTC 1-hour re-test
(OKX, ~16 months) did not change the verdicts.

## Web evidence round (2026-08-26, egress approved)

One search round (3 searches, 3 fetches) on the two open questions:

- **Premium selling has real, independent-adjacent support at the index
  level.** [[Bondarenko Put-Writing Study]] (Cboe-hosted, U. Illinois, 2019):
  over 32 years the PUT put-writing index matched the S&P 500's return
  (9.54% vs 9.80%/yr) at two-thirds the volatility (9.95% vs 14.93%) and
  −32.7% vs −50.9% max drawdown. Caveats: Cboe commissioned it, and PUT sells
  ATM monthly puts with no 45-DTE/50%-management/IV-rank mechanics — it
  supports the volatility-risk-premium idea, not tastylive's exact recipe.
- **A cautionary independent trial:** a retail trader's live test of modified
  tastytrade mechanics (~100 DTE, 35% profit target, high-IV names;
  sweetvolatility.com, retrieved 2026-08-26) hit the advertised ~70% win rate
  yet finished with negative P&L — win rate is not expectancy, and the
  modifications mean it is a weak counter-example, not a refutation.
- **Volume-profile/POC methods: no peer-reviewed support found.** The search
  surfaced only vendor and education sites; the one adjacent academic result
  (arXiv 2209.08825, 13F trading imbalances) is off-topic and, if anything,
  found imbalance-following unprofitable. The orderflow guide's claims remain
  without independent evidence.

Claim changes: "premium selling produces superior long-run risk-adjusted
returns" upgraded from unsupported to **provisional** (index-level evidence,
single commissioned source, mechanics differ); volume-profile claims stay
**unsupported**/**contested** as before.

## Contrasts and open questions

- The tastylive guide is process-first (formulas, management rules) and its
  arithmetic is verifiable; the CryptoSoulz guide is perception-first
  (read the live tape) and largely untestable from bars.
- Both are commercial documents; neither offers measured performance.
- Open: whether tastylive's specific 45-DTE/50%-management mechanics beat
  plain systematic put-writing (needs a mechanics-faithful backtest); whether
  orderflow tools add value intraday with real depth/footprint data.

See the [[index|Wiki Index]].
