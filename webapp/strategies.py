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
    key = (len(c), str(c.index[-1]), float(c.iloc[-1]), float(v.iloc[-1]), nodes)
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
