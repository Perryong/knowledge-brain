#!/usr/bin/env python3
"""
trade-check :: offline self-test

Builds synthetic Alpha Vantage payloads in a throwaway cache directory and runs
av_fetch.py --offline | check_rules.py against them. Verifies the pipeline and
the rule logic without spending a single API call.

    python3 selftest.py            # run all scenarios
    python3 selftest.py --show clean   # print the full scorecard for one case

Scenarios: clean, extended, distribution, below-ma200, loss-making, no-intraday.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sessions(n):
    """n business-ish days ending today, ascending."""
    out = []
    day = date.today()
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= timedelta(days=1)
    return list(reversed(out))


def daily_payload(symbol, closes, volumes, last_bar):
    dates = sessions(len(closes))
    series = {}
    for i, (d, c, v) in enumerate(zip(dates, closes, volumes)):
        if i == len(closes) - 1:
            o, h, l, cl = last_bar
        else:
            o, h, l, cl = c * 0.995, c * 1.01, c * 0.99, c
        series[d] = {
            "1. open": f"{o:.4f}",
            "2. high": f"{h:.4f}",
            "3. low": f"{l:.4f}",
            "4. close": f"{cl:.4f}",
            "5. volume": str(int(v)),
        }
    return {"Meta Data": {"2. Symbol": symbol}, "Time Series (Daily)": series}


def intraday_payload(symbol, vwap_target, close, bars=78):
    """Build 5-min bars whose cumulative VWAP lands on vwap_target."""
    series = {}
    stamp = datetime.combine(date.fromisoformat(sessions(1)[0]), datetime.min.time()).replace(hour=9, minute=35)
    for i in range(bars):
        # oscillate around the target, then walk to `close` at the end
        wobble = math.sin(i / 6.0) * vwap_target * 0.004
        price = vwap_target + wobble
        if i == bars - 1:
            price = close
        series[stamp.strftime("%Y-%m-%d %H:%M:%S")] = {
            "1. open": f"{price:.4f}",
            "2. high": f"{price * 1.001:.4f}",
            "3. low": f"{price * 0.999:.4f}",
            "4. close": f"{price:.4f}",
            "5. volume": "100000",
        }
        stamp += timedelta(minutes=5)
    return {"Meta Data": {"2. Symbol": symbol}, "Time Series (5min)": series}


def overview_payload(symbol, pe_ttm, pe_fwd, shares):
    return {
        "Symbol": symbol,
        "Name": f"{symbol} Test Corp",
        "Sector": "TECHNOLOGY",
        "Industry": "SEMICONDUCTORS",
        "Currency": "USD",
        "LatestQuarter": "2026-06-30",
        "TrailingPE": "None" if pe_ttm is None else f"{pe_ttm}",
        "PERatio": "None" if pe_ttm is None else f"{pe_ttm}",
        "ForwardPE": "0" if pe_fwd is None else f"{pe_fwd}",
        "EPS": "4.2",
        "ProfitMargin": "0.271",
        "QuarterlyRevenueGrowthYOY": "0.312",
        "QuarterlyEarningsGrowthYOY": "0.402",
        "SharesOutstanding": str(shares),
        "MarketCapitalization": "1000000000",
    }


def build(scenario):
    """-> (symbol, overview, daily, intraday) for a scenario."""
    n = 260
    symbol = scenario.upper().replace("-", "")

    if scenario == "clean":
        # steady uptrend inside the MA200 safe zone, pulled back onto MA10,
        # green candle on heavy volume
        closes = [50 + i * 0.08 for i in range(n)]
        closes[-1] = closes[-2] * 0.995          # small pullback toward MA10
        vols = [1_000_000] * n
        vols[-1] = 2_000_000                     # volume ratio 2.0
        c = closes[-1]
        last = (c * 0.985, c * 1.005, c * 0.98, c)   # green, decent lower wick
        return symbol, overview_payload(symbol, 30, 20, 100_000_000), \
            daily_payload(symbol, closes, vols, last), intraday_payload(symbol, c * 0.995, c)

    if scenario == "extended":
        closes = [50 * (1.012 ** i) for i in range(n)]   # parabolic
        vols = [1_000_000] * n
        vols[-1] = 2_000_000
        c = closes[-1]
        last = (c * 0.99, c * 1.01, c * 0.985, c)
        return symbol, overview_payload(symbol, 30, 20, 100_000_000), \
            daily_payload(symbol, closes, vols, last), intraday_payload(symbol, c * 0.999, c)

    if scenario == "distribution":
        closes = [50 + i * 0.25 for i in range(n)]
        vols = [1_000_000] * n
        vols[-1] = 3_000_000
        c = closes[-1] * 0.96
        closes[-1] = c
        last = (c * 1.04, c * 1.045, c * 0.995, c)      # big red candle
        return symbol, overview_payload(symbol, 30, 20, 100_000_000), \
            daily_payload(symbol, closes, vols, last), intraday_payload(symbol, c * 1.02, c)

    if scenario == "dip-below-ema21":
        # uptrend (EMA12 > EMA21) but the last close has dropped under EMA21:
        # pullback not yet bought -> rule 3 fails softly -> wait
        closes = [50 + i * 0.08 for i in range(n)]
        closes[-1] = closes[-2] * 0.95
        vols = [1_000_000] * n
        vols[-1] = 2_000_000
        c = closes[-1]
        last = (c * 0.985, c * 1.005, c * 0.98, c)
        return symbol, overview_payload(symbol, 30, 20, 100_000_000), \
            daily_payload(symbol, closes, vols, last), intraday_payload(symbol, c * 0.995, c)

    if scenario == "below-ma200":
        closes = [150 - i * 0.35 for i in range(n)]      # downtrend
        vols = [1_000_000] * n
        c = closes[-1]
        last = (c * 0.99, c * 1.005, c * 0.98, c)
        return symbol, overview_payload(symbol, 20, 30, 100_000_000), \
            daily_payload(symbol, closes, vols, last), intraday_payload(symbol, c * 1.01, c)

    if scenario == "loss-making":
        closes = [50 + i * 0.08 for i in range(n)]
        closes[-1] = closes[-2] * 0.995
        vols = [1_000_000] * n
        vols[-1] = 2_000_000
        c = closes[-1]
        last = (c * 0.985, c * 1.005, c * 0.98, c)
        return symbol, overview_payload(symbol, None, None, 100_000_000), \
            daily_payload(symbol, closes, vols, last), intraday_payload(symbol, c * 0.995, c)

    if scenario == "no-intraday":
        closes = [50 + i * 0.08 for i in range(n)]
        closes[-1] = closes[-2] * 0.995
        vols = [1_000_000] * n
        vols[-1] = 2_000_000
        c = closes[-1]
        last = (c * 0.985, c * 1.005, c * 0.98, c)
        return symbol, overview_payload(symbol, 30, 20, 100_000_000), \
            daily_payload(symbol, closes, vols, last), None

    raise SystemExit(f"unknown scenario {scenario!r}")


def build_tiingo(scenario):
    """Raw Tiingo payloads for the fallback scenario: same market shape as
    'clean', but served from Tiingo caches with NO Alpha Vantage cache at all."""
    n = 260
    closes = [50 + i * 0.08 for i in range(n)]
    closes[-1] = closes[-2] * 0.995
    vols = [1_000_000] * n
    vols[-1] = 2_000_000
    c = closes[-1]
    dates = sessions(n)

    daily = []
    for i, (d, cl, v) in enumerate(zip(dates, closes, vols)):
        if i == n - 1:
            o, h, l = c * 0.985, c * 1.005, c * 0.98
        else:
            o, h, l = cl * 0.995, cl * 1.01, cl * 0.99
        daily.append({
            "date": f"{d}T00:00:00.000Z",
            "adjOpen": o, "adjHigh": h, "adjLow": l, "adjClose": cl, "adjVolume": v,
            "open": o, "high": h, "low": l, "close": cl, "volume": v,
            "divCash": 0.0, "splitFactor": 1.0,
        })

    intraday = []
    stamp = datetime.combine(date.fromisoformat(dates[-1]), datetime.min.time()).replace(hour=14, minute=35)
    for i in range(78):
        wobble = math.sin(i / 6.0) * c * 0.995 * 0.004
        price = c * 0.995 + wobble
        if i == 77:
            price = c
        intraday.append({
            "date": stamp.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "open": price, "high": price * 1.001, "low": price * 0.999,
            "close": price, "volume": 100000.0,
        })
        stamp += timedelta(minutes=5)

    fundamentals = [{"date": f"{dates[-1]}T00:00:00.000Z", "marketCap": c * 100_000_000, "peRatio": 30.0, "pbRatio": 10.0}]
    return scenario.upper().replace("-", ""), fundamentals, daily, intraday


def seed_cache(cache_dir: Path, symbol, function, payload, suffix=""):
    name = function + (f"_{suffix}" if suffix else "")
    path = cache_dir / symbol / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "_fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "_fetched_at_epoch": datetime.now(timezone.utc).timestamp(),
        "_params": {"function": function, "symbol": symbol},
        "payload": payload,
    }))


SCENARIOS = ["clean", "extended", "dip-below-ema21", "distribution", "below-ma200", "loss-making",
             "no-intraday", "tiingo-fallback"]
EXPECTED = {
    "clean": "enter-candidate",
    # Parabolic but EMA12 > EMA21 and above EMA21: the EMA rule (2026-08-24) has no
    # extension cap -- backtested as a continuation buy; MA200 distance is a note only.
    "extended": "enter-candidate",
    "dip-below-ema21": "wait",
    "distribution": "avoid",
    "below-ma200": "avoid",
    "loss-making": "wait",
    "no-intraday": "wait",
    # Tiingo has no forward P/E, so rule 2 stays unknown -> wait, honestly.
    "tiingo-fallback": "wait",
}


def run(scenario, cache_root: Path, show=False):
    cache = cache_root / scenario
    if scenario == "tiingo-fallback":
        symbol, fundamentals, t_daily, t_intraday = build_tiingo(scenario)
        seed_cache(cache, symbol, "TIINGO_FUNDAMENTALS", fundamentals)
        seed_cache(cache, symbol, "TIINGO_DAILY", t_daily)
        seed_cache(cache, symbol, "TIINGO_INTRADAY", t_intraday, "5min")
    else:
        symbol, overview, daily, intraday = build(scenario)
        seed_cache(cache, symbol, "OVERVIEW", overview)
        seed_cache(cache, symbol, "TIME_SERIES_DAILY", daily, "full")
        if intraday:
            seed_cache(cache, symbol, "TIME_SERIES_INTRADAY", intraday, "5min")

    metrics_path = cache / "metrics.json"
    fetch = subprocess.run(
        [sys.executable, str(HERE / "av_fetch.py"), symbol, "--offline",
         "--cache-dir", str(cache), "--out", str(metrics_path)],
        capture_output=True, text=True,
    )
    if fetch.returncode != 0:
        return scenario, "ERROR", fetch.stderr.strip()

    check = subprocess.run(
        [sys.executable, str(HERE / "check_rules.py"), str(metrics_path),
         "--business", "pass", "--format", "json"],
        capture_output=True, text=True,
    )
    try:
        card = json.loads(check.stdout)
    except json.JSONDecodeError:
        return scenario, "ERROR", (check.stderr or check.stdout).strip()[:400]

    if show:
        md = subprocess.run(
            [sys.executable, str(HERE / "check_rules.py"), str(metrics_path), "--business", "pass"],
            capture_output=True, text=True,
        )
        print(md.stdout)
    return scenario, card["verdict"], card["verdict_reason"]


def run_backtest_tools(root: Path):
    """bt_prepare.py must emit a parseable engine for every strategy and
    bt_report.py must render a synthetic metrics.csv — no network, no vibe-trading."""
    import ast
    for strategy in ("ema", "ma200", "breakout", "squeeze", "macd", "value", "pocbounce", "emaflow", "hvnbreak", "lvnreject", "pocshift", "hlhvn"):
        out = subprocess.run(
            [sys.executable, str(HERE / "bt_prepare.py"), "TEST", "--strategy", strategy, "--max-hold-days", "126",
             "--end", "2026-01-01", "--run-root", str(root)], capture_output=True, text=True)
        if out.returncode:
            return "backtest-tools", "ERROR", out.stderr.strip()[:400]
        run_dir = Path(out.stdout.strip())
        ast.parse((run_dir / "code" / "signal_engine.py").read_text())
        cfg = json.loads((run_dir / "config.json").read_text())
        assert cfg["codes"] == ["TEST.US"] and cfg["end_date"] == "2026-01-01", cfg
    art = run_dir / "artifacts"
    art.mkdir()
    (art / "metrics.csv").write_text("total_return,sharpe,trade_count,win_rate\n0.5,1.2,10,0.4\n")
    (art / "trades.csv").write_text("timestamp,side,holding_days,return_pct\n2025-01-01,sell,90,20.0\n")
    rep = subprocess.run([sys.executable, str(HERE / "bt_report.py"), str(run_dir)], capture_output=True, text=True)
    grid = subprocess.run([sys.executable, str(HERE / "bt_report.py"), "--grid", str(run_dir)], capture_output=True, text=True)
    ok = (rep.returncode == 0 and "| Total return | +50% |" in rep.stdout and "+20.0%" in rep.stdout
          and grid.returncode == 0 and "| TEST | +50% / 1.20 / 10 /" in grid.stdout)
    return "backtest-tools", "ok" if ok else "FAIL", rep.stdout[-300:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", choices=SCENARIOS, help="print the full scorecard for one scenario")
    args = parser.parse_args()

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        targets = [args.show] if args.show else SCENARIOS
        for scenario in targets:
            name, verdict, reason = run(scenario, root, show=bool(args.show))
            expected = EXPECTED[scenario]
            ok = verdict == expected
            failures += 0 if ok else 1
            mark = "ok  " if ok else "FAIL"
            print(f"{mark} {name:<14} verdict={verdict:<16} (expected {expected})")
            if not ok or args.show:
                print(f"       {reason}")
        if not args.show:
            name, verdict, reason = run_backtest_tools(root / "bt")
            ok = verdict == "ok"
            failures += 0 if ok else 1
            print(f"{'ok  ' if ok else 'FAIL'} {name:<14} verdict={verdict:<16} (expected ok)")
            if not ok:
                print(f"       {reason}")
    print("\nall scenarios behaved as expected" if not failures else f"\n{failures} scenario(s) off-spec")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())