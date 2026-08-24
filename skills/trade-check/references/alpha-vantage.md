# Alpha Vantage data pipeline

How `scripts/av_fetch.py` turns three API responses into the inputs the
5-point checklist needs, and what it refuses to do.

## Setup

```bash
export ALPHAVANTAGE_API_KEY=your_key_here      # never pass the key on the command line
```

Put the export in your shell profile, or in a `.env` the vault does not sync.
A key pasted into a chat, a note, or a committed file should be treated as
burned — rotate it at <https://www.alphavantage.co/support/#api-key>.

## Calls made per ticker

| # | Function | Params | Feeds |
|---|----------|--------|-------|
| 1 | `OVERVIEW` | — | TTM P/E, forward P/E, shares outstanding, sector, margins, revenue growth |
| 2 | `TIME_SERIES_DAILY` | `outputsize=full` | close, MA10/20/30/50/200 + slopes, candle OHLC, volume ratio |
| 3 | `TIME_SERIES_INTRADAY` | `interval=5min`, `extended_hours=false` | session VWAP, VWAP slope, reclaim detection |

`--skip-intraday` drops call 3 and leaves rule 4 `unknown`.

## Rate limits

The free tier allows **25 requests/day** (5/min). Three calls per ticker means
roughly **8 tickers/day**. Mitigations built in:

- Responses are cached under `~/.cache/trade-check/alphavantage/<SYMBOL>/`
  (override with `--cache-dir` or `TRADE_CHECK_CACHE`).
- `--cache-ttl` defaults to 3600s. Re-running a ticker within the hour costs
  nothing. `--cache-ttl 0` forces a refetch.
- `--offline` re-derives metrics from cached payloads and never touches the
  network — use it when re-scoring with different thresholds.

Alpha Vantage reports limit exhaustion inside an HTTP 200 body under `Note` or
`Information`. The fetcher raises on those keys instead of parsing a stub, so a
throttled call becomes a `missing` input, never a fabricated one.

## Field mapping and known gaps

| Metric | Derivation | Gap to watch |
|--------|-----------|--------------|
| TTM P/E | `TrailingPE`, falling back to `PERatio` | `"None"` or ≤ 0 for loss-makers → null |
| Forward P/E | `ForwardPE` | frequently `"0"` (= unavailable) → null, not zero |
| MA10/20/30/50/200 | simple mean of the last *n* daily closes | needs ≥ 200 sessions; `outputsize=full` |
| MA30 slope | MA30 now vs MA30 five sessions back, in % | flat/negative = trend failure risk |
| Candle | latest daily bar; body and wicks as % of the session range | zero-range bars leave wick fields null |
| Volume ratio | today's volume ÷ mean of the **prior** 20 sessions | today is excluded from the baseline |
| Turnover % | volume ÷ `SharesOutstanding` × 100 | null whenever OVERVIEW omits share count |
| VWAP | Σ(typical × volume) ÷ Σ volume over the latest intraday session, typical = (H+L+C)/3 | regular hours only |
| Reclaim | session low < VWAP **and** session close > VWAP | needs intraday bars |

Two structural limits worth knowing before you trust a scorecard:

1. **Free-tier `TIME_SERIES_DAILY` is unadjusted.** A split or large dividend
   inside the 200-session window distorts every MA. Check for recent corporate
   actions on anything that split lately.
2. **Alpha Vantage's forward P/E is a stale consensus snapshot**, not a live
   estimate, and it is missing more often than not. When it is null, rule 2 is
   `unknown` — supply a figure from your own source if you want it scored.

Alpha Vantage's US coverage is good; non-US listings need the exchange suffix
(`D05.SIN`, `0700.HK`) and intraday data for them is often unavailable, which
leaves VWAP `unknown`.

## Output contract

`trade-check.metrics.v1` — every numeric field is nullable, and anything null is
also listed in `missing`. `sources[]` records, per API function, whether the
payload came from `api`, `cache`, or failed, plus the fetch timestamp and cache
path. `warnings[]` carries anything the scorecard reader should know (short
history, session-date mismatch between VWAP and the daily bar, absent share
count).

## Tiingo fallback

With `TIINGO_API_KEY` set, any failed Alpha Vantage call is rebuilt from
Tiingo (`api.tiingo.com`), converted into the same payload shapes, and cached
raw under the same tree as `TIINGO_*` entries:

| Input | Tiingo endpoint | Notes |
|-------|-----------------|-------|
| Daily bars | `/tiingo/daily/<SYM>/prices` | uses **adjusted** fields — actually better around splits than free AV |
| Intraday → VWAP | `/iex/<SYM>/prices` | IEX feed; VWAP is a close approximation of the consolidated figure |
| Fundamentals | `/tiingo/fundamentals/<SYM>/daily` | free tier is **Dow-30 only**; trailing P/E and marketCap only — **no forward P/E exists on Tiingo**, and shares outstanding is derived from marketCap ÷ close |

A full Tiingo-only run therefore scores rules 3–5 normally but leaves rule 2
`unknown` unless the user supplies the P/E figures. Free Tiingo quota
(~1,000 requests/day) dwarfs Alpha Vantage's 25, so the fallback rarely
compounds a quota problem.

## Verifying an install without spending calls

```bash
SKILL_DIR="$PRODUCT_ROOT/skills/trade-check"
python3 "$SKILL_DIR/scripts/selftest.py"            # six synthetic scenarios, no network
python3 "$SKILL_DIR/scripts/selftest.py" --show clean
```

Scenarios cover a clean entry, an extended trend, distribution, a broken MA200,
a loss-maker with no P/E, and a missing intraday feed. Each asserts an expected
verdict, so the self-test is also the regression test after any threshold or
rule edit.