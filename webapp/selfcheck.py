#!/usr/bin/env python3
"""Offline gate for the webapp. Run: python3 webapp/selfcheck.py  (exit 0 = pass)."""
import sys
import numpy as np
import pandas as pd

FAILURES = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILURES.append(name)


def fixture(n=400, trend=0.4, seed=7):
    """Synthetic daily bars: gentle uptrend with noise, volume spikes every 9 bars."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(trend, 1.2, n))
    close = np.maximum(close, 5.0)
    o = close * (1 + rng.normal(0, 0.004, n))
    h = np.maximum(o, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    l = np.minimum(o, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    v = np.where(np.arange(n) % 9 == 0, 2_000_000, 1_000_000).astype(float)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
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
    check("breakout: no lookahead (truncated history equals prefix)",
          REGISTRY["breakout"]["generate"](df.iloc[:300]).equals(
              REGISTRY["breakout"]["generate"](df).iloc[:300]))


def main():
    sys.path.insert(0, "webapp")
    run_registry_checks()
    print("\n%d failure(s)" % len(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
