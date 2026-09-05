---
type: research
title: Orderflow Strategy Backtest Grid
status: evergreen
created: 2026-08-26
updated: 2026-08-26
tags:
  - research
  - trading
  - backtest
  - order-flow
---

# Orderflow Strategy Backtest Grid

Saved conversation result (2026-08-24 analysis, filed 2026-08-26): the full
comparison of the four [[CryptoSoulz Orderflow Guide]]-derived strategies
against the vault's EMA12/EMA21 rule 3. Own backtests via the Vibe-Trading
MCP — daily bars 2016-08 → 2026-08 (ARM/NBIS shorter: listed 2023/2024),
$1M, 0.1% commission, rules 4–5 of the [[Investment Entry Checklist]] gating
every entry, 6-month hold cap, fills at signal-bar close. Artifacts:
`~/.vibe-trading/runs/<TICKER>-<strategy>-h126/`.

## Results — total return / Sharpe / trades / avg hold

| ticker | `ema` (rule 3) | `hvnbreak` | `lvnreject` | `pocshift` | `hlhvn` | buy & hold |
|---|---|---|---|---|---|---|
| NVDA | +2145% / 1.05 / 36 / 42d | +234% / 0.65 / 25 / 27d | +100% / 0.42 / 51 / 12d | +42% / 0.66 / 12 / 5d | +286% / 0.79 / 7 / 70d | +13746% |
| XAUUSD | +126% / 0.72 / 33 / 36d | +28% / 0.60 / 8 / 30d | +30% / 0.33 / 77 / 11d | −1% / 1 trade | −4% / 1 trade | +254% |
| BTC-USDT | +3367% / 1.12 / 44 / 34d | +74% / 0.36 / 48 / 17d | +398% / 0.75 / 47 / 17d | +11% / 3 trades | +337% / 0.87 / 6 / 80d | +1474% |
| ARM | +336% / 1.11 / 10 / 39d | +4% / 0.25 / 7 / 28d | +146% / 1.12 / 12 / 11d | no trades | +23% / 0.37 / 4 / 38d | +283% |
| NBIS | +487% / 1.51 / 6 / 49d | +145% / 1.11 / 5 / 32d | +21% / 0.44 / 8 / 15d | 1 trade | 1 trade (−20%) | +996% |
| VOO | +134% / 0.88 / 31 / 52d | +31% / 0.43 / 24 / 31d | +32% / 0.41 / 54 / 15d | −3% / 16 trades | +47% / 0.51 / 11 / 89d | +253% |
| TSLA | +3014% / 1.05 / 32 / 38d | +261% / 0.54 / 29 / 27d | +535% / 0.85 / 32 / 13d | −16% / 5 trades | +612% / 0.80 / 7 / 85d | +2374% |

## Max drawdown

| ticker | ema | hvnbreak | lvnreject | pocshift | hlhvn |
|---|---|---|---|---|---|
| NVDA | −40% | −32% | −34% | −7% | −43% |
| XAUUSD | −15% | −6% | −20% | −1% | −4% |
| BTC-USDT | −56% | −48% | −39% | −11% | −27% |
| ARM | −48% | −49% | −30% | 0% | −41% |
| NBIS | −55% | −41% | −47% | −7% | −27% |
| VOO | −14% | −13% | −20% | −8% | −19% |
| TSLA | −47% | −60% | −28% | −17% | −36% |

## Assessment

- **hlhvn** (higher low at an HVN, guide p.29) — *provisional*: the only one
  whose holds (70–89 d) match the 3–6 month swing horizon; best drawdowns on
  BTC/TSLA (−27%/−36% vs ema −56%/−47%), but 1–11 trades and losses on
  gold/NBIS. Kept as an optional filter.
- **lvnreject** (p.25) — *provisional*: good drawdowns, beats ema on ARM, but
  11–17 d holds and 50–77 trades — a scalp, not a swing rule.
- **hvnbreak** (p.28) — *contested*: positive but always below plain ema; the
  HVN adds nothing to an EMA filter on daily bars.
- **pocshift** (p.23) — *unsupported*: almost never fires.
- Counter-position: the source is a sales document for intraday tools; every
  daily proxy is a shadow of the real object, and a BTC 1-hour re-run did not
  rescue them.

**Verdict: nothing beats EMA12/EMA21 on the swing horizon** — consistent with
the earlier batch (`value`, `pocbounce`, `emaflow`), making eight
guide-derived strategies tested in total. Claim grades live in the ledger via
[[Options Income and Orderflow Research]]; concept context in
[[Volume and Market Profile]].

See the [[index|Wiki Index]].
