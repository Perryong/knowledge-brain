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
