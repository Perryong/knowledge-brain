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
    import requests
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
