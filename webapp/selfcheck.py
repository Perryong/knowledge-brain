#!/usr/bin/env python3
"""Offline gate for the webapp. Run: python3 webapp/selfcheck.py  (exit 0 = pass)."""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

FAILURES = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILURES.append(name)


def fixture(n=400, trend=0.4, seed=7, end=None):
    """Synthetic daily bars: gentle uptrend with noise, volume spikes every 9 bars.
    Ends on `end` (default: today) so scan_all's freshness check sees a live series;
    pass an older `end` (e.g. 30 days ago) to fabricate a deliberately stale one."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(trend, 1.2, n))
    close = np.maximum(close, 5.0)
    o = close * (1 + rng.normal(0, 0.004, n))
    h = np.maximum(o, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    l = np.minimum(o, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    v = np.where(np.arange(n) % 9 == 0, 2_000_000, 1_000_000).astype(float)
    idx = pd.bdate_range(end=pd.Timestamp(end) if end is not None else pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": close, "volume": v}, index=idx)


def run_registry_checks():
    from strategies import REGISTRY, sig_state, triggers
    names = {"ema", "ma200", "breakout", "squeeze", "macd", "value", "pocbounce",
             "emaflow", "hvnbreak", "lvnreject", "pocshift", "hlhvn", "smcstruct", "ewabc"}
    check("registry has all 14 strategies", set(REGISTRY) == names)
    df = fixture()
    for name, spec in REGISTRY.items():
        sig = spec["generate"](df)
        check(f"{name}: aligned index", sig.index.equals(df.index))
        check(f"{name}: values in {{0,1}}", set(np.unique(sig.values)) <= {0.0, 1.0})
        check(f"{name}: has buy/sell text", bool(spec["buy"]) and bool(spec["sell"]))
    # ema must be long somewhere on a trending fixture and produce a BUY flip
    ema_sig = REGISTRY["ema"]["generate"](df)
    check("ema: enters on uptrend fixture", ema_sig.max() == 1.0)
    flips = (ema_sig.diff() == 1.0)
    i = flips[flips].index[0]
    upto = ema_sig.loc[:i]
    check("ema: BUY reported at first flip", sig_state(upto) == ("holding", "BUY"))
    check("ema: triggers dict", isinstance(triggers("ema", df), dict))
    check("smcstruct: triggers dict", isinstance(triggers("smcstruct", df), dict))
    a1 = REGISTRY["value"]["generate"](df)
    a2 = REGISTRY["value"]["generate"](df)
    check("profile cache: repeat call identical", a1.equals(a2))
    check("profile cache: different data not reused",
          not REGISTRY["value"]["generate"](fixture(seed=11)).equals(a1))
    tail_a = fixture(seed=3)
    tail_b = tail_a.copy()
    tail_b.iloc[50:150, tail_b.columns.get_loc("close")] *= 1.35
    tail_b.iloc[50:150, tail_b.columns.get_loc("high")] *= 1.35
    tail_b.iloc[50:150, tail_b.columns.get_loc("low")] *= 1.35
    from strategies import volume_profile
    poc_a = volume_profile(tail_a["high"], tail_a["low"], tail_a["close"], tail_a["volume"])[0]
    poc_b = volume_profile(tail_b["high"], tail_b["low"], tail_b["close"], tail_b["volume"])[0]
    check("profile cache: identical tails with different history are distinct",
          not poc_a.dropna().equals(poc_b.dropna()))
    check("breakout: no lookahead (truncated history equals prefix)",
          REGISTRY["breakout"]["generate"](df.iloc[:300]).equals(
              REGISTRY["breakout"]["generate"](df).iloc[:300]))


def run_fetch_checks():
    import scan
    wl = scan.load_universe()
    check("universe: 62 entries", len(wl) == 62)
    check("universe: fields", all({"name", "source", "code", "sector"} <= set(e) for e in wl))
    check("universe: sources known", all(e["source"] in ("yfinance", "okx") for e in wl))
    check("universe: unique names", len({e["name"] for e in wl}) == len(wl))
    check("universe: 12 sector groups", len({e["sector"] for e in wl}) == 12)
    check("universe: originals present",
          {"NVDA", "XAUUSD", "BTCUSDT", "ARM", "NBIS", "VOO", "TSLA"} <= {e["name"] for e in wl})
    batches = scan.batches([{"code": str(i)} for i in range(45)], 20)
    check("batching: 45 -> 3 chunks", [len(b) for b in batches] == [20, 20, 5])
    # normalizer is pure: OKX candle rows -> DataFrame (no network).
    # Real OKX returns rows newest-first, so the fixture does too: this way the
    # ascending/values checks actually exercise okx_rows_to_df's .sort_index().
    rows = [["1712102400000", "105", "112", "99", "108", "6", "600", "1", "1"],
            ["1712016000000", "100", "110", "90", "105", "5", "500", "1", "1"]]
    df = scan.okx_rows_to_df(rows)
    check("okx normalizer: columns", list(df.columns) == ["open", "high", "low", "close", "volume"])
    check("okx normalizer: ascending", df.index.is_monotonic_increasing)
    check("okx normalizer: values", float(df["close"].iloc[-1]) == 108.0)


def run_scan_checks():
    import json
    import scan
    df = fixture()
    full = lambda entries, years=2: {e["name"]: df for e in entries}   # offline stub
    result = scan.scan_all(fetch=full)
    universe = scan.load_universe()
    check("scan: every universe name present", set(result["signals"]) == {e["name"] for e in universe})
    check("scan: no stale with stub", result["stale"] == [])
    nv = result["signals"]["NVDA"]
    check("scan: 14 strategies per ticker", len(nv) == 14)
    check("scan: state values", all(v["state"] in ("holding", "flat") for v in nv.values()))
    check("scan: action values", all(v["action"] in ("BUY", "SELL", "none") for v in nv.values()))
    check("scan: candles trimmed", len(result["candles"]["NVDA"]["d"]) <= 260)
    check("scan: candles carry strategy-generated levels",
          {"sh", "sl", "fvg"} <= set(result["candles"]["NVDA"]) and
          any(x is not None for x in result["candles"]["NVDA"]["sh"]))
    partial = lambda entries, years=2: {e["name"]: df for e in entries[:10]}
    r2 = scan.scan_all(fetch=partial)
    check("scan: missing names marked stale", len(r2["stale"]) == len(universe) - 10)
    # a frame whose last bar is ~30 days old must be treated exactly like a failed
    # fetch: dropped into "stale" with no signals/candles, never published as today's.
    old_df = fixture(end=date.today() - timedelta(days=30))
    stale_fetch = lambda entries, years=2: {e["name"]: old_df for e in entries}
    r3 = scan.scan_all(fetch=stale_fetch)
    check("scan: stale last bar (30d old) marked stale",
          set(r3["stale"]) == {e["name"] for e in universe})
    check("scan: stale tickers carry no signals/candles",
          all(r3["signals"][n] == {} for n in r3["stale"]) and r3["candles"] == {})
    # write_outputs()/build_page() must never touch the real docs/ during self-check
    # (finding 1): redirect scan.DOCS to a throwaway dir for the duration.
    real_docs = scan.DOCS
    try:
        with tempfile.TemporaryDirectory() as tmp:
            scan.DOCS = Path(tmp)
            scan.write_outputs(result)
            payload = json.loads((scan.DOCS / "data.json").read_text())
    finally:
        scan.DOCS = real_docs
    check("payload: keys", set(payload) == {"scan", "backtests", "history", "rules", "universe", "covered"})
    check("payload: universe carries sectors", all({"name", "sector"} <= set(u) for u in payload["universe"]))
    check("payload: covered is the backtested subset",
          set(payload["covered"]) == set(payload["backtests"]) and len(payload["covered"]) == 11)
    check("payload: history covers all 7 backtested tickers",
          set(payload["history"]) == set(payload["covered"]))
    check("payload: history curves non-empty for every covered ticker",
          all(payload["history"][t]["curves"] for t in payload["covered"]))
    check("payload: size under 4MB", len(json.dumps(payload)) < 4_000_000)


def run_page_checks():
    import json
    import scan, page
    df = fixture()
    # dict stub, matching what scan_all actually expects ({name: frame}) — the old
    # `lambda e, years=2: df` stub returned a bare DataFrame, so bars.get(name) was
    # always None, every ticker went stale, and the page built with zero candles.
    full = lambda entries, years=2: {e["name"]: df for e in entries}
    result = scan.scan_all(fetch=full)
    # sandbox docs/ writes (finding 1) for both scan.write_outputs and page.build_page
    real_scan_docs, real_page_docs = scan.DOCS, page.DOCS
    try:
        with tempfile.TemporaryDirectory() as tmp:
            scan.DOCS = page.DOCS = Path(tmp)
            scan.write_outputs(result)
            out = page.build_page()
            html = out.read_text()
    finally:
        scan.DOCS, page.DOCS = real_scan_docs, real_page_docs
    check("page: payload injected", "__PAYLOAD__" not in html and '"signals"' in html)
    check("page: signals panel present", 'id="sigmatrix"' in html)
    check("page: rules panel present", 'id="rules"' in html)
    check("page: rule text flows from registry", "A-B-C pullback" in html)
    check("page: sector picker present", 'id="picker"' in html and "optgroup" in html)
    check("page: sector filter present", 'id="sectorfilter"' in html)
    # these two fail against an empty payload: with the old bare-DataFrame stub every
    # ticker goes stale, so NVDA never gets a candles entry and its signals dict is {}.
    check("page: NVDA candle data embedded in html", '"NVDA":{"d":' in html)
    check("page: NVDA has a populated (non-empty) signal row", '"NVDA":{"ema":{"state":' in html)


def main():
    sys.path.insert(0, "webapp")
    run_registry_checks()
    run_fetch_checks()
    run_scan_checks()
    run_page_checks()
    print("\n%d failure(s)" % len(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
