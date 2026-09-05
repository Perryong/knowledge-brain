# Strategy Bench Webapp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a nightly signal scanner + GitHub Pages dashboard to this repo: run all 14 strategies over a ~60-name US sector universe on fresh daily bars, publish `docs/index.html` with a sector dropdown, and open a GitHub issue when a strategy flips BUY/SELL.

**Architecture:** A pure-pandas strategy registry (`webapp/strategies.py`) is the single source of truth for rules and rule text. `webapp/scan.py` fetches daily bars (yfinance/OKX, no keys), replays every engine over full history to get current state + today's action, and renders `docs/` from a committed HTML template. A scheduled GitHub Action runs the self-check, the scan, commits `docs/`, and files an issue on new signals.

**Tech Stack:** Python 3.11+ (pandas, numpy, yfinance, requests — CI only; no repo-vendored deps), vanilla-JS single-file HTML page, GitHub Actions + Pages.

**Spec:** `docs/superpowers/specs/2026-09-05-strategy-bench-webapp-design.md`

## Global Constraints

- No API keys anywhere; data sources are yfinance and OKX public candles only.
- Engines are long/flat, no lookahead: 10-bar confirmed pivots, windows exactly as in `skills/trade-check/scripts/bt_prepare.py` (D=1) — do not "improve" them.
- The scan never runs backtests; historical metrics come from committed `webapp/backtests.json`.
- `docs/` is the GitHub Pages root; `docs/index.html` and `docs/data.json` are build artifacts committed by the Action.
- A failed ticker fetch marks it `stale` and the scan continues; the run fails only if all fetches fail.
- Do not modify anything under `skills/trade-check/` or `MyKnowledgeVault/`.
- Universe is ~60 US names across 11 GICS sectors + a Macro group, defined in `webapp/universe.json` with a hardcoded `sector` field (no per-ticker metadata fetch).
- Equity bars are fetched in batches of ≤20 tickers; the 120-bar volume profile is cached per ticker and shared by the seven profile-using strategies. Nightly runtime target: under 5 minutes.
- Backtest history exists only for the seven originally backtested instruments (NVDA, XAUUSD, BTCUSDT, ARM, NBIS, VOO, TSLA); every other ticker is signals-only and the page must say so rather than render empty charts.
- Python files run with the system `python3`; CI installs `pandas numpy yfinance requests`.

---

### Task 1: Strategy registry (`webapp/strategies.py`)

**Files:**
- Create: `webapp/strategies.py`
- Create: `webapp/selfcheck.py` (first checks; later tasks append)

**Interfaces:**
- Produces: `REGISTRY: dict[str, dict]` with keys per strategy: `generate` (callable `(df: pd.DataFrame) -> pd.Series` of {0.0,1.0}, df columns `open,high,low,close,volume`, DatetimeIndex), `buy: str`, `sell: str`, `gated: bool`. Strategy names (exact): `ema, ma200, breakout, squeeze, macd, value, pocbounce, emaflow, hvnbreak, lvnreject, pocshift, hlhvn, smcstruct, ewabc`.
- Produces: `sig_state(sig: pd.Series) -> tuple[str, str]` returning `("holding"|"flat", "BUY"|"SELL"|"none")` from the last two values.
- Produces: `triggers(name: str, df: pd.DataFrame) -> dict | None` for `ema/smcstruct/ewabc` (see Step 3).

- [ ] **Step 1: Write the failing self-check**

Create `webapp/selfcheck.py`:

```python
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
    # a tail-only cache key silently returns another frame's profile: prove it cannot
    from strategies import volume_profile
    tail_a = fixture(seed=3)
    tail_b = tail_a.copy()
    for col in ("close", "high", "low"):
        tail_b.iloc[50:150, tail_b.columns.get_loc(col)] *= 1.35
    poc_a = volume_profile(tail_a["high"], tail_a["low"], tail_a["close"], tail_a["volume"])[0]
    poc_b = volume_profile(tail_b["high"], tail_b["low"], tail_b["close"], tail_b["volume"])[0]
    check("profile cache: identical tails with different history are distinct",
          not poc_a.dropna().equals(poc_b.dropna()))
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 webapp/selfcheck.py`
Expected: exits non-zero with `ModuleNotFoundError: No module named 'strategies'`.

- [ ] **Step 3: Write `webapp/strategies.py`**

The engine bodies are ports of `skills/trade-check/scripts/bt_prepare.py`'s ENGINE template with `D=1` and the default thresholds, plus the smcstruct/ewabc engines. Write exactly:

```python
"""Strategy registry: single source of truth for rules and rule text.

Every generate(df) takes daily OHLCV (DatetimeIndex) and returns a Series in
{0.0, 1.0} aligned to df.index. Long/flat, no lookahead. Ports of the engines
backtested via skills/trade-check (D=1, default thresholds) — keep in sync by
hand; do not import from skills/.
"""
import numpy as np
import pandas as pd

PULLBACK_BAND = 0.03
MA200_SAFE_ZONE = 0.20
VOL_RATIO_INST = 1.5
LONG_LOWER_WICK = 0.40
VWAP_WINDOW = 20
MAX_HOLD = 126
PROFILE_WINDOW, PROFILE_BINS, VALUE_AREA = 120, 50, 0.70
HVN_RATIO, LVN_RATIO = 1.5, 0.5
W = 10  # pivot confirmation window (smcstruct/ewabc/hlhvn)


def _ctx(df):
    c, o, h, l, v = df["close"], df["open"], df["high"], df["low"], df["volume"]
    tp = (h + l + c) / 3
    vwap = (tp * v).rolling(VWAP_WINDOW).sum() / v.rolling(VWAP_WINDOW).sum()
    vol_ratio = v / v.rolling(20).mean()
    rng = (h - l).replace(0, np.nan)
    lower_wick = (np.minimum(o, c) - l) / rng
    e12 = c.ewm(span=12, adjust=False).mean()
    e21 = c.ewm(span=21, adjust=False).mean()
    rule4 = c > vwap
    rule5 = (c > o) & ((vol_ratio >= VOL_RATIO_INST) | (lower_wick >= LONG_LOWER_WICK))
    return c, o, h, l, v, e12, e21, rule4, rule5


def _hold(df, entry, exit_, max_hold=MAX_HOLD):
    entry = pd.Series(entry, index=df.index).fillna(False).to_numpy()
    exit_ = pd.Series(exit_, index=df.index).fillna(False).to_numpy()
    sig = np.zeros(len(df))
    holding, held = False, 0
    for i in range(len(df)):
        if holding:
            held += 1
            if exit_[i] or (max_hold and held >= max_hold):
                holding = False
        elif entry[i]:
            holding, held = True, 0
        sig[i] = 1.0 if holding else 0.0
    return pd.Series(sig, index=df.index)


_PROFILE_CACHE = {}  # fingerprint -> result; keeps the scan from recomputing per strategy


def volume_profile(h, l, c, v, nodes=False):
    key = (len(c), str(c.index[-1]), float(c.iloc[-1]), float(v.iloc[-1]),
           float(c.sum()), float(v.sum()), float(h.sum()), float(l.sum()), nodes)
    hit = _PROFILE_CACHE.get(key)
    if hit is not None:
        return hit
    tp = ((h + l + c) / 3).to_numpy()
    hi, lo, vol, cl = h.to_numpy(), l.to_numpy(), v.to_numpy(), c.to_numpy()
    n = len(tp)
    poc = np.full(n, np.nan); vah = np.full(n, np.nan); val = np.full(n, np.nan)
    rc, hc, rl, ll, hl2 = (np.full(n, np.nan) for _ in range(5))
    prev = None
    for i in range(PROFILE_WINDOW - 1, n):
        if nodes and prev is not None:
            p_hist, p_edges = prev
            mean_bin = p_hist.mean()
            for price, r_out, lo_out, hi_out in ((cl[i], rc, None, hc), (lo[i], rl, ll, hl2)):
                k = int(np.clip(np.searchsorted(p_edges, price, side="right") - 1, 0, PROFILE_BINS - 1))
                r_out[i] = p_hist[k] / mean_bin if mean_bin > 0 else np.nan
                hi_out[i] = p_edges[k + 1]
                if lo_out is not None:
                    lo_out[i] = p_edges[k]
        s = slice(i - PROFILE_WINDOW + 1, i + 1)
        edges = np.linspace(lo[s].min(), hi[s].max(), PROFILE_BINS + 1)
        hist, _ = np.histogram(tp[s], bins=edges, weights=vol[s])
        if hist.sum() <= 0:
            continue
        mids = (edges[:-1] + edges[1:]) / 2
        k = int(hist.argmax())
        a = b = k
        acc, target = hist[k], hist.sum() * VALUE_AREA
        while acc < target and (a > 0 or b < PROFILE_BINS - 1):
            up = hist[b + 1] if b < PROFILE_BINS - 1 else -1
            dn = hist[a - 1] if a > 0 else -1
            if up >= dn:
                b += 1; acc += up
            else:
                a -= 1; acc += dn
        poc[i], vah[i], val[i] = mids[k], edges[b + 1], edges[a]
        prev = (hist, edges)
    idx = h.index
    out = (pd.Series(poc, idx), pd.Series(vah, idx), pd.Series(val, idx))
    if nodes:
        out += (pd.Series(rc, idx), pd.Series(hc, idx), pd.Series(rl, idx),
                pd.Series(ll, idx), pd.Series(hl2, idx))
    if len(_PROFILE_CACHE) > 4:
        _PROFILE_CACHE.clear()
    _PROFILE_CACHE[key] = out
    return out


def _swings(df):
    """Confirmed swing series: last swing high/low as of each bar (W bars late)."""
    h, l = df["high"], df["low"]
    hi_roll = h.rolling(2 * W + 1).max().to_numpy()
    lo_roll = l.rolling(2 * W + 1).min().to_numpy()
    hn, ln = h.to_numpy(), l.to_numpy()
    n = len(df)
    sh = np.full(n, np.nan); sl = np.full(n, np.nan)
    last_sh = last_sl = np.nan
    for i in range(n):
        if i >= 2 * W:
            if hn[i - W] == hi_roll[i]:
                last_sh = hn[i - W]
            if ln[i - W] == lo_roll[i]:
                last_sl = ln[i - W]
        sh[i], sl[i] = last_sh, last_sl
    return pd.Series(sh, df.index), pd.Series(sl, df.index)


def g_ema(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    return _hold(df, (e12 > e21) & r4 & r5, e12 < e21)


def g_ma200(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    ma10, ma50, ma200 = c.rolling(10).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    above = (c > ma200) & (c / ma200 - 1 <= MA200_SAFE_ZONE)
    at_ma = ((c / ma10 - 1).abs() <= PULLBACK_BAND) | ((c / ma50 - 1).abs() <= PULLBACK_BAND)
    return _hold(df, above & at_ma & r4 & r5, c < ma200)


def g_breakout(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    return _hold(df, (c > h.rolling(55).max().shift(1)) & r4 & r5,
                 c < l.rolling(20).min().shift(1))


def g_squeeze(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    width = (4 * sd) / mid
    tight = (width.rolling(120).min() == width).rolling(5).max().fillna(0).astype(bool)
    return _hold(df, tight & (c > mid + 2 * sd) & r4 & r5, c < e21)


def g_macd(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    macd = e12 - c.ewm(span=26, adjust=False).mean()
    sigl = macd.ewm(span=9, adjust=False).mean()
    cross = (macd > sigl) & (macd.shift(1) <= sigl.shift(1)) & (c > c.ewm(span=50, adjust=False).mean())
    return _hold(df, cross & r4 & r5, macd < sigl)


def _delta5(df):
    c, l, h, v = df["close"], df["low"], df["high"], df["volume"]
    rng = (h - l).replace(0, np.nan)
    return (v * (2 * (c - l) / rng - 1)).rolling(5).sum()


def g_value(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    poc, vah, val = volume_profile(df["high"], df["low"], c, v)
    poc1, vah1 = poc.shift(1), vah.shift(1)
    accepted = (c > vah1) & (c.shift(1) > vah1.shift(1))
    return _hold(df, accepted & (poc1 > poc1.shift(20)) & (_delta5(df) > 0) & r4 & r5, c < poc1)


def g_pocbounce(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    poc, vah, val = volume_profile(df["high"], df["low"], c, v)
    poc1, val1 = poc.shift(1), val.shift(1)
    at_poc = (c >= poc1) & (c / poc1 - 1 <= PULLBACK_BAND)
    return _hold(df, (e12 > e21) & at_poc & (_delta5(df) > 0) & r4 & r5, c < val1)


def g_emaflow(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    poc, vah, val = volume_profile(df["high"], df["low"], c, v)
    return _hold(df, (e12 > e21) & (_delta5(df) > 0) & (c > poc.shift(1)) & r4 & r5, e12 < e21)


def g_hvnbreak(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    poc, vah, val, rc, hc, rl, ll, hl2 = volume_profile(df["high"], df["low"], c, v, nodes=True)
    entry = (rc.shift(1) >= HVN_RATIO) & (c > hc.shift(1)) & (_delta5(df) > 0) & r4 & r5
    return _hold(df, entry, c < poc.shift(1))


def g_lvnreject(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    poc, vah, val, rc, hc, rl, ll, hl2 = volume_profile(df["high"], df["low"], c, v, nodes=True)
    entry = (rl <= LVN_RATIO) & (c > hl2) & r4 & r5
    floor = ll.where(entry).ffill()
    return _hold(df, entry, c < floor)


def g_pocshift(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    poc, vah, val = volume_profile(df["high"], df["low"], c, v)
    poc1, vah1, val1 = poc.shift(1), vah.shift(1), val.shift(1)
    rising = (poc1 > poc1.shift(5)) & (poc1.shift(5) > poc1.shift(10))
    entry = rising & (c > poc1) & (c <= vah1) & (_delta5(df) > 0) & r4 & r5
    return _hold(df, entry, (c < val1) | (poc1 <= poc1.shift(10)))


def g_hlhvn(df):
    c, o, h, l, v, e12, e21, r4, r5 = _ctx(df)
    poc, vah, val, rc, hc, rl, ll, hl2 = volume_profile(df["high"], df["low"], c, v, nodes=True)
    low = df["low"]
    swing = low.shift(W) == low.rolling(2 * W + 1).min()
    swing_low = low.shift(W).where(swing)
    prev_swing = swing_low.ffill().shift(1).where(swing)
    higher = (swing_low > prev_swing) & (rl.shift(W) >= HVN_RATIO)
    state = higher.where(swing).ffill().infer_objects(copy=False).fillna(False).astype(bool)
    stop = swing_low.where(swing).ffill()
    entry = state & (c > e21) & (c > stop) & (_delta5(df) > 0) & r4 & r5
    return _hold(df, entry, c < stop)


def g_smcstruct(df):
    c = df["close"]
    sh, sl = _swings(df)
    bull_fvg = (df["low"] > df["high"].shift(2)).rolling(20).max().fillna(0)
    return _hold(df, (c > sh) & (bull_fvg > 0), c < sl)


def g_ewabc(df):
    c, h, l = df["close"], df["high"], df["low"]
    n = len(df)
    hi_roll = h.rolling(2 * W + 1).max().to_numpy()
    lo_roll = l.rolling(2 * W + 1).min().to_numpy()
    hn, ln = h.to_numpy(), l.to_numpy()
    cn = c.to_numpy()
    sig = np.zeros(n)
    pivots = []
    last_sl = np.nan
    holding, held = False, 0
    for i in range(n):
        if i >= 2 * W:
            if hn[i - W] == hi_roll[i] and (not pivots or pivots[-1][0] != 1):
                pivots.append((1, hn[i - W]))
            if ln[i - W] == lo_roll[i] and (not pivots or pivots[-1][0] != -1):
                pivots.append((-1, ln[i - W]))
                last_sl = ln[i - W]
        if holding:
            held += 1
            if (not np.isnan(last_sl) and cn[i] < last_sl) or held >= MAX_HOLD:
                holding = False
        elif len(pivots) >= 3:
            k2, p2 = pivots[-1]; k1, p1 = pivots[-2]; k0, p0 = pivots[-3]
            if k0 == -1 and k1 == 1 and k2 == -1 and p2 > p0 and cn[i] > p1:
                holding, held = True, 0
        sig[i] = 1.0 if holding else 0.0
    return pd.Series(sig, index=df.index)


_G45 = "green candle with volume ≥1.5× 20d avg or lower wick ≥40%, close > 20d VWAP"

REGISTRY = {
    "ema":       {"generate": g_ema,       "gated": True,  "buy": f"EMA12 > EMA21 and {_G45}",                              "sell": "EMA12 closes below EMA21, or 126 sessions"},
    "ma200":     {"generate": g_ma200,     "gated": True,  "buy": f"price > MA200 (≤20% above), within 3% of MA10/MA50, {_G45}", "sell": "close < MA200, or 126 sessions"},
    "breakout":  {"generate": g_breakout,  "gated": True,  "buy": f"close > prior 55-day high, {_G45}",                     "sell": "close < prior 20-day low, or 126 sessions"},
    "squeeze":   {"generate": g_squeeze,   "gated": True,  "buy": f"Bollinger(20,2) width at 120d low, close > upper band, {_G45}", "sell": "close < EMA21, or 126 sessions"},
    "macd":      {"generate": g_macd,      "gated": True,  "buy": f"MACD(12,26,9) crosses above signal with close > EMA50, {_G45}", "sell": "MACD < signal, or 126 sessions"},
    "value":     {"generate": g_value,     "gated": True,  "buy": f"2 closes above 120d value-area high, POC rising 20d, 5d delta > 0, {_G45}", "sell": "close < POC, or 126 sessions"},
    "pocbounce": {"generate": g_pocbounce, "gated": True,  "buy": f"EMA12 > EMA21, close at/just above 120d POC, 5d delta > 0, {_G45}", "sell": "close < value-area low, or 126 sessions"},
    "emaflow":   {"generate": g_emaflow,   "gated": True,  "buy": f"EMA12 > EMA21, 5d delta > 0, close > 120d POC, {_G45}", "sell": "EMA12 < EMA21, or 126 sessions"},
    "hvnbreak":  {"generate": g_hvnbreak,  "gated": True,  "buy": f"close breaks above the high-volume node it sat in, 5d delta > 0, {_G45}", "sell": "close < POC, or 126 sessions"},
    "lvnreject": {"generate": g_lvnreject, "gated": True,  "buy": f"low prints in a low-volume node and close recovers above it, {_G45}", "sell": "close < that node's floor, or 126 sessions"},
    "pocshift":  {"generate": g_pocshift,  "gated": True,  "buy": f"POC rising 5d and 10d, close inside value above POC, 5d delta > 0, {_G45}", "sell": "close < value-area low or POC stalls 10d, or 126 sessions"},
    "hlhvn":     {"generate": g_hlhvn,     "gated": True,  "buy": f"confirmed higher swing low inside a high-volume node, close > EMA21, 5d delta > 0, {_G45}", "sell": "close < that swing low, or 126 sessions"},
    "smcstruct": {"generate": g_smcstruct, "gated": False, "buy": "close breaks last 10-bar swing high (BOS/CHoCH) with a bullish FVG in the last 20 bars", "sell": "close < last 10-bar swing low, or 126 sessions"},
    "ewabc":     {"generate": g_ewabc,     "gated": False, "buy": "A-B-C pullback completes as a higher low and close breaks the interior high", "sell": "close < last confirmed swing low, or 126 sessions"},
}


def sig_state(sig):
    last = float(sig.iloc[-1]) if len(sig) else 0.0
    prev = float(sig.iloc[-2]) if len(sig) > 1 else 0.0
    state = "holding" if last == 1.0 else "flat"
    action = "BUY" if (last, prev) == (1.0, 0.0) else "SELL" if (last, prev) == (0.0, 1.0) else "none"
    return state, action


def triggers(name, df):
    c = df["close"]
    last = float(c.iloc[-1])
    if name in ("ema", "emaflow"):
        e12 = float(c.ewm(span=12, adjust=False).mean().iloc[-1])
        e21 = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
        return {"ema12": round(e12, 4), "ema21": round(e21, 4),
                "gap_pct": round((e12 / e21 - 1) * 100, 2)}
    if name in ("smcstruct", "ewabc"):
        sh, sl = _swings(df)
        shv = sh.iloc[-1]; slv = sl.iloc[-1]
        out = {}
        if not np.isnan(slv):
            out["swing_low"] = round(float(slv), 4)
            out["to_exit_pct"] = round((float(slv) / last - 1) * 100, 2)
        if name == "smcstruct" and not np.isnan(shv):
            out["swing_high"] = round(float(shv), 4)
            out["to_entry_pct"] = round((float(shv) / last - 1) * 100, 2)
        return out
    return None
```

- [ ] **Step 4: Run the self-check to verify it passes**

Run: `python3 webapp/selfcheck.py`
Expected: exit 0, every line `ok`, `0 failure(s)`.

- [ ] **Step 5: Commit**

```bash
git add webapp/strategies.py webapp/selfcheck.py
git commit -m "feat(webapp): strategy registry with rule text + offline self-check"
```

---

### Task 2: Sector universe + bar fetchers (`webapp/scan.py`, part 1)

**Files:**
- Create: `webapp/universe.json`
- Create: `webapp/scan.py` (fetch layer only)
- Modify: `webapp/selfcheck.py` (append fetch-layer checks — offline only)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `load_universe() -> list[dict]` (each `{"name","source","code","sector"}`); `fetch_all(entries, years=2) -> dict[str, pd.DataFrame]` (batched yfinance downloads of ≤20 tickers + per-entry OKX calls; missing names simply absent); `fetch_bars(entry, years=2) -> pd.DataFrame | None` (single-ticker path with 3 retries, used by tests and as the batch fallback); `okx_daily(inst, years=2) -> pd.DataFrame`; `okx_rows_to_df(rows) -> pd.DataFrame`.

- [ ] **Step 1: Generate `webapp/universe.json`**

Run this once and commit the output (the sector map is the source of truth; edit it to grow the universe):

```bash
mkdir -p webapp && python3 - <<'EOF'
import json
from pathlib import Path

SECTORS = {
    "Information Technology": ["NVDA", "MSFT", "AAPL", "AVGO", "AMD", "ARM", "NBIS"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "T"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "Consumer Staples":       ["PG", "KO", "COST", "WMT", "PEP"],
    "Health Care":            ["LLY", "UNH", "JNJ", "ABBV", "MRK"],
    "Financials":             ["BRK-B", "JPM", "V", "MA", "BAC"],
    "Industrials":            ["CAT", "GE", "UBER", "BA", "HON"],
    "Energy":                 ["XOM", "CVX", "COP", "SLB", "EOG"],
    "Materials":              ["LIN", "SHW", "FCX", "NEM", "APD"],
    "Utilities":              ["NEE", "SO", "DUK", "CEG", "AEP"],
    "Real Estate":            ["PLD", "AMT", "EQIX", "SPG", "O"],
}
rows = [{"name": t, "source": "yfinance", "code": t, "sector": s}
        for s, ts in SECTORS.items() for t in ts]
rows += [
    {"name": "XAUUSD",  "source": "yfinance", "code": "GC=F",     "sector": "Macro"},
    {"name": "BTCUSDT", "source": "okx",      "code": "BTC-USDT", "sector": "Macro"},
    {"name": "VOO",     "source": "yfinance", "code": "VOO",      "sector": "Macro"},
]
Path("webapp/universe.json").write_text(json.dumps(rows, indent=1))
print(len(rows), "entries,", len(SECTORS) + 1, "groups")
EOF
```

Expected: `60 entries, 12 groups`.

- [ ] **Step 2: Append failing offline checks to `webapp/selfcheck.py`**

Add below `run_registry_checks()` and call from `main()` before the failure count:

```python
def run_fetch_checks():
    import scan
    wl = scan.load_universe()
    check("universe: 60 entries", len(wl) == 60)
    check("universe: fields", all({"name", "source", "code", "sector"} <= set(e) for e in wl))
    check("universe: sources known", all(e["source"] in ("yfinance", "okx") for e in wl))
    check("universe: unique names", len({e["name"] for e in wl}) == len(wl))
    check("universe: 12 sector groups", len({e["sector"] for e in wl}) == 12)
    check("universe: originals present",
          {"NVDA", "XAUUSD", "BTCUSDT", "ARM", "NBIS", "VOO", "TSLA"} <= {e["name"] for e in wl})
    batches = scan.batches([{"code": str(i)} for i in range(45)], 20)
    check("batching: 45 -> 3 chunks", [len(b) for b in batches] == [20, 20, 5])
    # normalizer is pure: OKX candle rows -> DataFrame (no network)
    rows = [["1712016000000", "100", "110", "90", "105", "5", "500", "1", "1"],
            ["1712102400000", "105", "112", "99", "108", "6", "600", "1", "1"]]
    df = scan.okx_rows_to_df(rows)
    check("okx normalizer: columns", list(df.columns) == ["open", "high", "low", "close", "volume"])
    check("okx normalizer: ascending", df.index.is_monotonic_increasing)
    check("okx normalizer: values", float(df["close"].iloc[-1]) == 108.0)
```

- [ ] **Step 3: Run to verify it fails**

Run: `python3 webapp/selfcheck.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'scan'`.

- [ ] **Step 4: Write the fetch layer in `webapp/scan.py`**

```python
#!/usr/bin/env python3
"""Nightly signal scan: fetch daily bars, replay every strategy, render docs/.

Run locally:  python3 webapp/scan.py   then open docs/index.html
In CI, --github-output appends new_signals=<summary> to $GITHUB_OUTPUT.
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DOCS = REPO / "docs"


def load_universe():
    return json.loads((HERE / "universe.json").read_text())


def batches(seq, size):
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def okx_rows_to_df(rows):
    """OKX candle rows (newest first): [ts_ms, o, h, l, c, vol, ...] -> OHLCV frame."""
    recs = [(pd.Timestamp(int(r[0]), unit="ms"), float(r[1]), float(r[2]),
             float(r[3]), float(r[4]), float(r[5])) for r in rows]
    df = pd.DataFrame(recs, columns=["ts", "open", "high", "low", "close", "volume"])
    return df.set_index("ts").sort_index()


def okx_daily(inst, years=2):
    import requests          # lazy: keeps the offline selfcheck pandas/numpy-only
    frames, after = [], ""
    cutoff = pd.Timestamp(date.today() - timedelta(days=365 * years))
    for _ in range(12):  # 12 * 100 bars > 3 years
        url = f"https://www.okx.com/api/v5/market/history-candles?instId={inst}&bar=1D&limit=100{after}"
        rows = requests.get(url, timeout=20).json().get("data", [])
        if not rows:
            break
        frames.append(okx_rows_to_df(rows))
        oldest = int(rows[-1][0])
        if pd.Timestamp(oldest, unit="ms") < cutoff:
            break
        after = f"&after={oldest}"
        time.sleep(0.25)
    df = pd.concat(frames).sort_index()
    return df[~df.index.duplicated()].loc[cutoff:]


def yf_daily(code, years=2):
    import yfinance as yf
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    df = yf.download(code, start=start, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    return df[["open", "high", "low", "close", "volume"]].dropna()


def yf_batch(codes, years=2):
    """One download for many tickers -> {code: OHLCV frame}. Missing codes are omitted."""
    import yfinance as yf
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    raw = yf.download(" ".join(codes), start=start, progress=False,
                      auto_adjust=True, group_by="ticker", threads=True)
    out = {}
    for code in codes:
        try:
            df = raw[code] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df.copy()
            df.columns = [str(c).lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].dropna()
            if len(df) >= 260:
                out[code] = df
        except Exception as e:  # noqa: BLE001 — one bad ticker must not sink the batch
            print(f"warn: batch miss {code}: {e}", file=sys.stderr)
    return out


def fetch_all(entries, years=2):
    """Batched fetch for the whole universe -> {name: frame}; absent name == stale."""
    bars = {}
    yf_entries = [e for e in entries if e["source"] == "yfinance"]
    for chunk in batches(yf_entries, 20):
        got = yf_batch([e["code"] for e in chunk], years)
        for e in chunk:
            if e["code"] in got:
                bars[e["name"]] = got[e["code"]]
        time.sleep(1)
    for e in entries:
        if e["name"] in bars:
            continue
        df = fetch_bars(e, years)          # retry path for batch misses and OKX
        if df is not None:
            bars[e["name"]] = df
    return bars


def fetch_bars(entry, years=2):
    for attempt in range(3):
        try:
            df = okx_daily(entry["code"], years) if entry["source"] == "okx" \
                else yf_daily(entry["code"], years)
            if len(df) >= 260:
                return df
            raise ValueError(f"only {len(df)} bars")
        except Exception as e:  # noqa: BLE001 — any fetch failure retries then goes stale
            print(f"warn: {entry['name']} attempt {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None
```

- [ ] **Step 5: Run self-check to verify it passes**

Run: `python3 webapp/selfcheck.py`
Expected: exit 0, all `ok`.

- [ ] **Step 6: One manual online smoke (not part of selfcheck)**

Run: `python3 -c "import sys; sys.path.insert(0,'webapp'); import scan; b=scan.fetch_all(scan.load_universe()[:5]); print(len(b), {k: len(v) for k,v in b.items()})"`
Expected: 5 frames of ≥ 260 bars each. (Skip without failing the task if the network is blocked; CI exercises it nightly.)

- [ ] **Step 7: Commit**

```bash
git add webapp/universe.json webapp/scan.py webapp/selfcheck.py
git commit -m "feat(webapp): sector universe + batched daily-bar fetchers (yfinance/OKX)"
```

---

### Task 3: Signal computation + `docs/data.json` (`webapp/scan.py`, part 2)

**Files:**
- Modify: `webapp/scan.py` (append)
- Modify: `webapp/selfcheck.py` (append)
- Create: `webapp/backtests.json` (baked historical grid)

**Interfaces:**
- Consumes: `REGISTRY`, `sig_state`, `triggers` (Task 1); `load_universe`, `fetch_all` (Task 2).
- Produces: `scan_all(fetch=fetch_all) -> dict` returning
  `{"as_of": "YYYY-MM-DD", "stale": [names], "signals": {tname: {sname: {"state","action","trigger"}}}, "candles": {tname: {"d","o","h","l","c"}}, "fills": {}}`. `fetch` takes the entry list and returns `{name: DataFrame}` (so batching lives in the fetcher, not the loop).
- Produces: `write_outputs(result: dict) -> list[str]` — writes `docs/data.json` as `{"scan","backtests","rules","universe","covered"}` where `universe` is `[{"name","sector"}]` and `covered` lists the names that have backtest history; returns `["TICKER·strat BUY", ...]` for fresh actions.

- [ ] **Step 1: Bake `webapp/backtests.json`**

Run this one-off (requires the historical runs on this machine; commit the output):

```bash
python3 - <<'EOF'
import csv, json
from pathlib import Path
RUNS = Path.home() / ".vibe-trading" / "runs"
TICKERS = ["NVDA","XAUUSD","BTCUSDT","ARM","NBIS","VOO","TSLA"]
STRATS = ["ema-h126","ma200-h126","breakout-h126","squeeze-h126","macd-h126","value-h126",
          "pocbounce-h126","emaflow-h126","hvnbreak-h126","lvnreject-h126","pocshift-h126",
          "hlhvn-h126","smcstruct","ewabc"]
out = {}
for t in TICKERS:
    out[t] = {}
    for s in STRATS:
        p = RUNS / f"{t}-{s}" / "artifacts" / "metrics.csv"
        if not p.exists():
            continue
        row = next(csv.DictReader(open(p)))
        g = lambda k: float(row[k]) if row.get(k) not in (None, "", "[]") else None
        out[t][s.replace("-h126","")] = {"ret": g("total_return"), "sharpe": g("sharpe"),
            "dd": g("max_drawdown"), "trades": int(float(row["trade_count"])),
            "win": g("win_rate"), "hold": g("avg_holding_days"), "bh": g("benchmark_return"),
            "pf": g("profit_factor")}
Path("webapp/backtests.json").write_text(json.dumps(out, separators=(",",":")))
print("ok", sum(len(v) for v in out.values()), "cells")
EOF
```

Expected: `ok` with ≥ 90 cells.

- [ ] **Step 2: Append failing checks to `webapp/selfcheck.py`**

```python
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
    partial = lambda entries, years=2: {e["name"]: df for e in entries[:10]}
    r2 = scan.scan_all(fetch=partial)
    check("scan: missing names marked stale", len(r2["stale"]) == len(universe) - 10)
    scan.write_outputs(result)
    payload = json.loads((scan.DOCS / "data.json").read_text())
    check("payload: keys", set(payload) == {"scan", "backtests", "rules", "universe", "covered"})
    check("payload: universe carries sectors", all({"name", "sector"} <= set(u) for u in payload["universe"]))
    check("payload: covered is the backtested subset",
          set(payload["covered"]) == set(payload["backtests"]) and len(payload["covered"]) == 7)
    check("payload: size under 4MB", len(json.dumps(payload)) < 4_000_000)
```

(If importing `fixture` from within the module is awkward, move `fixture()` to module top level — it already is.)

- [ ] **Step 3: Run to verify it fails**

Run: `python3 webapp/selfcheck.py`
Expected: FAIL with `AttributeError: module 'scan' has no attribute 'scan_all'`.

- [ ] **Step 4: Append to `webapp/scan.py`**

```python
sys.path.insert(0, str(HERE))
from strategies import REGISTRY, sig_state, triggers  # noqa: E402

CANDLE_BARS = 260
TRIGGER_STRATS = ("ema", "smcstruct", "ewabc")


def scan_all(fetch=fetch_all):
    entries = load_universe()
    bars = fetch(entries)
    result = {"as_of": date.today().isoformat(), "stale": [], "signals": {}, "candles": {}, "fills": {}}
    for entry in entries:
        name = entry["name"]
        df = bars.get(name)
        result["signals"][name] = {}
        if df is None:
            result["stale"].append(name)
            continue
        tail = df.tail(CANDLE_BARS)
        r = 4 if float(df["close"].iloc[-1]) < 100 else 2
        result["candles"][name] = {
            "d": [d.strftime("%Y-%m-%d") for d in tail.index],
            "o": [round(float(x), r) for x in tail["open"]],
            "h": [round(float(x), r) for x in tail["high"]],
            "l": [round(float(x), r) for x in tail["low"]],
            "c": [round(float(x), r) for x in tail["close"]],
        }
        for sname, spec in REGISTRY.items():
            sig = spec["generate"](df)
            state, action = sig_state(sig)
            cell = {"state": state, "action": action}
            if sname in TRIGGER_STRATS:
                cell["trigger"] = triggers(sname, df)
            result["signals"][name][sname] = cell
    return result


def write_outputs(result):
    DOCS.mkdir(exist_ok=True)
    backtests = json.loads((HERE / "backtests.json").read_text())
    rules = {n: {"buy": s["buy"], "sell": s["sell"], "gated": s["gated"]} for n, s in REGISTRY.items()}
    universe = [{"name": e["name"], "sector": e["sector"]} for e in load_universe()]
    payload = {"scan": result, "backtests": backtests, "rules": rules,
               "universe": universe, "covered": sorted(backtests)}
    (DOCS / "data.json").write_text(json.dumps(payload, separators=(",", ":")))
    fresh = [f"{t}·{s} {v['action']}"
             for t, m in result["signals"].items()
             for s, v in m.items() if v["action"] != "none"]
    return fresh


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    result = scan_all()
    if result["stale"] and len(result["stale"]) == len(load_universe()):
        print("error: every fetch failed", file=sys.stderr)
        return 1
    fresh = write_outputs(result)
    from page import build_page  # Task 4
    build_page()
    line = ", ".join(fresh)
    print(f"as_of={result['as_of']} stale={','.join(result['stale']) or '-'} new_signals={line or '-'}")
    if "--github-output" in argv:
        import os
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as f:
                f.write(f"new_signals={line}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run self-check to verify it passes**

Run: `python3 webapp/selfcheck.py`
Expected: exit 0, all `ok`. (`main()` is not exercised by selfcheck — `build_page` arrives in Task 4.)

- [ ] **Step 6: Commit**

```bash
git add webapp/scan.py webapp/selfcheck.py webapp/backtests.json
git commit -m "feat(webapp): signal scan core — states, actions, triggers, docs/data.json"
```

---

### Task 4: Page builder (`webapp/page.py` + template)

**Files:**
- Create: `webapp/template.html` (from the existing built dashboard)
- Create: `webapp/page.py`
- Modify: `webapp/selfcheck.py` (append)

**Interfaces:**
- Consumes: `docs/data.json` payload shape from Task 3 (`{"scan","backtests","rules"}`).
- Produces: `build_page() -> Path` — reads `docs/data.json`, writes `docs/index.html` (template with `/*__PAYLOAD__*/null` replaced by the JSON payload).

- [ ] **Step 1: Seed the template from the existing dashboard**

The current dashboard build lives in this session's scratchpad. Copy and de-data it:

```bash
mkdir -p webapp
cp "/private/tmp/claude-501/-Users-perry-Documents-Code-claude-obsidian/d1af83e6-02ce-45a1-a89e-a32eaffa7e60/scratchpad/webapp/strategy-bench.html" webapp/template.html
python3 - <<'EOF'
import re
from pathlib import Path
p = Path("webapp/template.html")
h = p.read_text()
h2, n = re.subn(r"const DATA = \{.*?\};\n", "const PAYLOAD = /*__PAYLOAD__*/null;\nconst DATA = PAYLOAD ? adapt(PAYLOAD) : null;\n", h, count=1, flags=re.S)
assert n == 1
p.write_text(h2)
print("template seeded,", len(h2), "bytes")
EOF
```

If the scratchpad file no longer exists, STOP and report — the template must come from the built dashboard, not be rewritten from scratch in this task.

- [ ] **Step 2: Add the adapter, sector picker, and new panels to the template**

**2a — panels.** Insert this as the FIRST panel in the body (before the equity panel):

```html
<div class="panel">
  <h2>Today's signals · <span id="asof"></span></h2>
  <div id="fresh" class="legend"></div>
  <div class="chips" style="margin:10px 0 6px">
    <label class="sub" for="sectorfilter">Sector</label>
    <select id="sectorfilter" onchange="render()"></select>
  </div>
  <div class="scroll"><table id="sigmatrix"></table></div>
</div>
<div class="panel">
  <h2>Strategy rules</h2>
  <div class="scroll"><table id="rules"></table></div>
</div>
```

**2b — instrument picker.** Replace the body's `<div class="chips" id="tickers">…</div>` control with:

```html
<div class="chips">
  <select id="picker" aria-label="Instrument" onchange="setTicker(this.value)"></select>
  <span id="favchips"></span>
</div>
```

Add matching CSS beside the existing `.chip` rules:

```css
select{font:600 12.5px Archivo,system-ui,sans-serif;color:var(--ink);background:var(--chip);
  border:1px solid var(--line);border-radius:8px;padding:6px 10px}
select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
```

**2c — script.** Define `adapt` (already referenced by the seeded `const DATA` line) and the new renderers, and replace the old `tickersBar()` body:

```js
const FAVOURITES = ["NVDA", "XAUUSD", "BTCUSDT", "ARM", "NBIS", "VOO", "TSLA"];
function adapt(p){
  // historical panels read: tickers, strategies, metrics, curves, trades, ohlc, fills
  return { tickers: p.universe.map(u => u.name), strategies: Object.keys(p.rules),
           metrics: p.backtests, curves: {}, trades: {}, fills: {},
           ohlc: p.scan.candles, scan: p.scan, rules: p.rules,
           universe: p.universe, covered: p.covered };
}
function sectorsOf(){
  const m = {};
  for (const u of DATA.universe) (m[u.sector] = m[u.sector] || []).push(u.name);
  return m;
}
function tickersBar(){                      // replaces the old chip-row renderer
  const groups = sectorsOf();
  document.getElementById("picker").innerHTML = Object.keys(groups).map(s =>
    `<optgroup label="${s}">` + groups[s].map(n =>
      `<option value="${n}" ${n===ticker?"selected":""}>${n}</option>`).join("") + `</optgroup>`).join("");
  document.getElementById("favchips").innerHTML = FAVOURITES.filter(n => DATA.tickers.includes(n))
    .map(n => `<button class="chip ${n===ticker?"on":""}" onclick="setTicker('${n}')">${n}</button>`).join("");
  const sel = document.getElementById("sectorfilter");
  if (!sel.options.length)
    sel.innerHTML = `<option value="ALL">All sectors</option>` +
      Object.keys(groups).map(s => `<option value="${s}">${s}</option>`).join("");
}
function covered(t){ return (DATA.covered || []).includes(t); }
function signalsPanel(){
  const s = DATA.scan;
  document.getElementById("asof").textContent =
    s.as_of + (s.stale.length ? ` · stale: ${s.stale.join(", ")}` : "");
  const fresh = [];
  for (const t in s.signals) for (const k in s.signals[t]){
    const v = s.signals[t][k];
    if (v.action !== "none") fresh.push(`<span><b class="${v.action==="BUY"?"pos":"neg"}">${v.action}</b> ${t} · ${k}</span>`);
  }
  document.getElementById("fresh").innerHTML = fresh.join("") || "<span>No new signals on the latest bar.</span>";
  const pick = document.getElementById("sectorfilter").value || "ALL";
  const rows = DATA.universe.filter(u => pick === "ALL" || u.sector === pick).map(u => u.name);
  const strats = DATA.strategies;
  document.getElementById("sigmatrix").innerHTML =
    `<tr><th>Ticker</th>${strats.map(x=>`<th>${x}</th>`).join("")}</tr>` +
    rows.map(t => `<tr><td>${t}</td>` + strats.map(k => {
      const v = (s.signals[t]||{})[k];
      if (!v) return `<td style="color:var(--ink-3)">–</td>`;
      const mark = v.action !== "none" ? ` <b class="${v.action==="BUY"?"pos":"neg"}">${v.action}</b>` : "";
      return `<td>${v.state === "holding" ? "●" : "○"}${mark}</td>`;
    }).join("") + "</tr>").join("");
}
function rulesPanel(){
  document.getElementById("rules").innerHTML =
    `<tr><th>Strategy</th><th>Buy when</th><th>Sell when</th></tr>` +
    Object.entries(DATA.rules).map(([n, r]) =>
      `<tr><td>${n}</td><td style="text-align:left;font-family:Archivo">${r.buy}</td>` +
      `<td style="text-align:left;font-family:Archivo">${r.sell}</td></tr>`).join("");
}
```

**2d — guard the historical panels.** `tiles()`, `chart()`, `gridTable()`, `heat()`, and `tradesTable()` index into data that exists only for the seven backtested names. Wrap each body's start with the coverage guard so a signals-only ticker renders a note instead of throwing:

```js
  if (!covered(ticker)) {
    $("tiles").innerHTML = `<div class="tile"><div class="k">Backtest history</div>` +
      `<div class="v">–</div><div class="d">${ticker} is signals-only; no backtest was run for it.</div></div>`;
    return;   // same shape in chart/gridTable/tradesTable, writing to their own element ids
  }
```

For `chart()` and `tradesTable()`, write `<i>No backtest history for ${ticker} — signals only.</i>` into `#chartwrap` / `#trades` and return. `heat()` always renders (it is universe-wide over `DATA.metrics`, which only holds covered names).

Wire the new renderers first in `render()`:

```js
function render(){ tickersBar(); signalsPanel(); rulesPanel(); tiles(); legend(); chart();
                   pcHeader(); priceChart(); gridTable(); heat(); tradesTable(); }
```

- [ ] **Step 3: Write `webapp/page.py`**

```python
"""Render docs/index.html from webapp/template.html + docs/data.json."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs"
MARK = "/*__PAYLOAD__*/null"


def build_page():
    payload = (DOCS / "data.json").read_text()
    html = (HERE / "template.html").read_text()
    assert html.count(MARK) == 1, "template payload marker missing"
    out = DOCS / "index.html"
    out.write_text(html.replace(MARK, payload))
    return out
```

- [ ] **Step 4: Append failing checks to `webapp/selfcheck.py`**

```python
def run_page_checks():
    import json
    import scan, page
    df = fixture()
    result = scan.scan_all(fetch=lambda e, years=2: df)
    scan.write_outputs(result)
    out = page.build_page()
    html = out.read_text()
    check("page: payload injected", "__PAYLOAD__" not in html and '"signals"' in html)
    check("page: signals panel present", 'id="sigmatrix"' in html)
    check("page: rules panel present", 'id="rules"' in html)
    check("page: rule text flows from registry", "A-B-C pullback" in html)
    check("page: sector picker present", 'id="picker"' in html and "optgroup" in html)
    check("page: sector filter present", 'id="sectorfilter"' in html)
```

Call `run_scan_checks()` and `run_page_checks()` from `main()`.

- [ ] **Step 5: Run self-check; verify pass**

Run: `python3 webapp/selfcheck.py`
Expected: exit 0 on the system interpreter (this is the dependency-light gate; it must keep passing with only pandas + numpy).

Then run the full local path ONCE with an interpreter that has `yfinance` and `requests` installed — the system `python3` does not, and must not be modified: `<py-with-net> webapp/scan.py`. This is the only pre-CI exercise of the live fetch path, and it is what puts REAL market data into `docs/data.json` before the first commit. Open `docs/index.html` in a browser — Today's signals matrix and Strategy rules render; historical panels show real backtest metrics for the seven covered names; a signals-only ticker shows its empty-state text.

Do not commit `docs/` while it holds self-check fixture output (all 60 tickers carrying identical synthetic bars). Verify before committing: `docs/data.json`'s `scan.as_of` is today and its candle dates are recent real trading days.

- [ ] **Step 6: Commit**

```bash
git add webapp/template.html webapp/page.py webapp/selfcheck.py docs/data.json docs/index.html
git commit -m "feat(webapp): page builder — sector picker, signals matrix, strategy rules"
```

---

### Task 5: GitHub Action (`.github/workflows/scan.yml`)

**Files:**
- Create: `.github/workflows/scan.yml`

**Interfaces:**
- Consumes: `python3 webapp/selfcheck.py` (exit code), `python3 webapp/scan.py --github-output` (writes `new_signals` to `$GITHUB_OUTPUT`; commits happen here, not in Python).

- [ ] **Step 1: Write the workflow**

```yaml
name: scan
on:
  schedule:
    - cron: "30 22 * * 1-5"   # weekdays after US close (UTC)
  workflow_dispatch:
permissions:
  contents: write
  issues: write
concurrency:
  group: scan
  cancel-in-progress: false
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pandas numpy yfinance requests
      - name: Self-check (abort if engines broken)
        run: python3 webapp/selfcheck.py
      - name: Scan
        id: scan
        run: python3 webapp/scan.py --github-output
      - name: Commit docs
        run: |
          git config user.name "strategy-bench-bot"
          git config user.email "actions@users.noreply.github.com"
          git add docs/data.json docs/index.html
          git diff --cached --quiet || git commit -m "scan: $(date -u +%F)"
          git push
      - name: Open signal issue
        if: steps.scan.outputs.new_signals != ''
        env:
          GH_TOKEN: ${{ github.token }}
          SIGNALS: ${{ steps.scan.outputs.new_signals }}
        run: |
          gh issue create \
            --title "Signals $(date -u +%F): $SIGNALS" \
            --label signal \
            --body "New signals from the nightly scan: $SIGNALS

          Dashboard: https://$(gh repo view --json owner,name -q '.owner.login').github.io/$(gh repo view --json name -q .name)/"
```

- [ ] **Step 2: Validate the YAML locally**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/scan.yml')); print('yaml ok')"` (if PyYAML is unavailable locally, `ruby -ryaml -e "YAML.load_file('.github/workflows/scan.yml'); puts 'yaml ok'"` or visual inspection + the first Actions run serves as validation).
Expected: `yaml ok`.

- [ ] **Step 3: Create the `signal` label (one-off, after the repo is on GitHub)**

Run: `gh label create signal --color FBCA04 --description "New strategy signal from nightly scan" || true`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/scan.yml
git commit -m "ci: nightly scan workflow — selfcheck, scan, publish docs, signal issue"
```

---

### Task 6: Enable Pages + README + first live run

**Files:**
- Modify: `README.md` (append a section; do not touch existing content)

**Interfaces:**
- Consumes: everything prior; requires the user to have made the repo public (their decision B — do NOT flip visibility yourself; confirm with the user it is done).

- [ ] **Step 1: Append to `README.md`**

```markdown
## Strategy Bench (webapp/)

Nightly signal scanner + dashboard for the swing strategies backtested in this repo.

- **Dashboard:** https://perryong.github.io/knowledge-brain/ (GitHub Pages from `docs/`)
- **Scan locally:** `pip install pandas numpy yfinance requests` then `python3 webapp/scan.py` and open `docs/index.html`
- **Cloud:** `.github/workflows/scan.yml` runs weekdays 22:30 UTC (and via Actions → scan → Run workflow), commits `docs/`, and opens a `signal`-labeled issue when any strategy flips BUY/SELL.
- **Universe:** ~60 US names across the 11 GICS sectors + Macro, in `webapp/universe.json` — pick one from the sector dropdown. Only the seven originally backtested instruments carry historical metrics; the rest are signals-only.
- **Rules:** `webapp/strategies.py` is the single source of truth; the page's rules panel renders from it.
- Not investment advice; signals are end-of-day and fills in the backtests assume no slippage.
```

- [ ] **Step 2: Commit and push**

```bash
git add README.md
git commit -m "docs: Strategy Bench usage"
git push
```

- [ ] **Step 3: Repo settings (user-confirmed, then via gh)**

Confirm with the user that flipping the repo public is still wanted, then:

```bash
gh repo edit Perryong/knowledge-brain --visibility public --accept-visibility-change-consequences
gh api -X POST repos/Perryong/knowledge-brain/pages -f build_type=legacy -f "source[branch]=main" -f "source[path]=/docs" || \
gh api -X PUT repos/Perryong/knowledge-brain/pages -f build_type=legacy -f "source[branch]=main" -f "source[path]=/docs"
```

- [ ] **Step 4: First live run + verify**

Run: `gh workflow run scan && sleep 90 && gh run list --workflow scan --limit 1`
Expected: run completes green; `docs/` commit appears; https://perryong.github.io/knowledge-brain/ serves the dashboard with a fresh `as_of` date; if any strategy flipped on the latest bar, one `signal` issue exists.

- [ ] **Step 5: Final commit check**

Run: `git status --short` — expected clean; `python3 webapp/selfcheck.py` — expected exit 0.

---

## Self-review notes

- Spec coverage: layout → Tasks 1–4; scan semantics → Tasks 1–3; sector universe + batching + profile cache → Tasks 1–3; page additions incl. sector dropdown and partial-coverage notes → Task 4; Action + issue → Task 5; running instructions + Pages + public flip → Task 6; stale path → Tasks 2–3; selfcheck gate → every task. Out-of-scope items untouched.
- Type consistency: `REGISTRY`/`sig_state`/`triggers` names match across Tasks 1, 3; `scan_all(fetch=...)`/`write_outputs`/`build_page` match across Tasks 3–5; payload keys `{"scan","backtests","rules"}` match Task 3 ↔ Task 4.
- Known session dependency: Task 4 Step 1 copies the template from this session's scratchpad path; if absent, the executor stops and reports (explicitly instructed).
