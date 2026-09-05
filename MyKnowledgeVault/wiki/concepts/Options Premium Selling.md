---
address: c-000012
type: concept
title: Options Premium Selling
status: developing
created: 2026-08-26
updated: 2026-08-26
tags:
  - concept
  - trading
  - options
---

# Options Premium Selling

The tastylive doctrine from the [[Tastylive Options Strategy Guide]]:
trade "where the stock will NOT go" by selling option premium instead of
betting on direction.

## The mechanics

1. **Sell when implied volatility is high.** Option premium = intrinsic +
   extrinsic value; extrinsic is inflated by IV and always decays to zero at
   expiry. Credit strategies are listed as "IV ENVIRONMENT: High" throughout
   the guide; debit and calendar trades want low IV.
2. **Enter ~45 days to expiration.** Theta decay accelerates while gamma risk
   stays manageable.
3. **Manage winners at 50% of max profit** (25% for straddles and
   butterflies). Do not hold through expiration; close or roll first.
4. **Defend, don't hope:** roll out in time or move strikes — always for a
   credit — before a short strike goes in the money.
5. **Choose the risk type consciously.** Undefined-risk trades (naked
   put/call, strangle, straddle) collect more premium; defined-risk versions
   (verticals, iron condor/fly, lizards) cap loss at spread width − credit.

## Evidence status

- Payoff formulas verified exactly against a live NVDA chain
  ([[Options Income and Orderflow Research]], 2026-08-25).
- Long-run performance: **provisional**. Systematic index put-writing matched
  the S&P 500's 32-year return at ~2/3 the volatility
  ([[Bondarenko Put-Writing Study]]), but that index uses none of the
  45-DTE/50% mechanics, the study was Cboe-commissioned, and one retail live
  trial went negative despite a 70% win rate. Win rate is not expectancy.

Related: [[Options Strategy Families]], [[Investment Entry Checklist]].

See the [[index|Wiki Index]].
