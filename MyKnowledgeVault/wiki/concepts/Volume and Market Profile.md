---
address: c-000014
type: concept
title: Volume and Market Profile
status: developing
created: 2026-08-26
updated: 2026-08-26
tags:
  - concept
  - trading
  - order-flow
---

# Volume and Market Profile

From the [[CryptoSoulz Orderflow Guide]] (pp.15–17, 21–25). Volume Profile
maps traded volume *by price*; Market Profile maps *time* at price (TPOs).

## Vocabulary

- **POC (Point of Control):** the price with the most traded volume (or most
  time, in Market Profile) — the market's "fair price" for the window.
- **HVN / LVN (High/Low Volume Node):** heavy-volume shelves act as
  support/resistance magnets; thin zones let price move fast.
- **Value Area:** the range holding ~70% of traded volume; VAH/VAL are its
  edges. Acceptance above VAH is bullish, below VAL bearish.

## Claimed setups and their tested status

Backtests (daily-bar proxies, 7 instruments, 2016–2026 — see
[[Options Income and Orderflow Research]]):

- Higher low at an HVN (p.29): **provisional** — best of the four tested,
  3–6 month holds, but sparse (1–11 trades) and mixed across instruments.
- HVN breakout with buyer pressure (p.28): **contested** — positive but
  strictly worse than the plain EMA12/EMA21 rule everywhere.
- Rising-POC value entry (p.23): rarely fires on daily bars.
- No peer-reviewed independent evidence for POC methods was found in the
  2026-08-25 web round.

Rule 3 of the [[Investment Entry Checklist]] remains EMA12/EMA21; the
profile tools are context, not gates. Related: [[Moving Averages]].

See the [[index|Wiki Index]].
