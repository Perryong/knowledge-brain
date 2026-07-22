#!/usr/bin/env python3
"""Compute technical indicators over fetched market data. Stdlib only, no network.

Reads .raw/market-data/YYYY-MM-DD/<label>.json (from fetch-market.py) and writes
<label>.analysis.json next to it. The numbers here are trustworthy (deterministic);
the narrative layer (autoresearch) is model output and must be read as such.

Usage:
  python3 scripts/analyze-market.py [YYYY-MM-DD]   # default: latest dated dir
  python3 scripts/analyze-market.py --selfcheck
"""
import glob, json, os, sys

VAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sma(closes, n):
    return round(sum(closes[-n:]) / n, 4) if len(closes) >= n else None


def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(-n, 0):                       # seed over the last n deltas
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_gain, avg_loss = gains / n, losses / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def atr(bars, n=14):
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return round(sum(trs[-n:]) / n, 4)


def pct(closes, n):
    return round((closes[-1] / closes[-1 - n] - 1) * 100, 2) if len(closes) > n else None


def ytd(bars):
    year = bars[-1]["datetime"][:4]
    first = next((b for b in bars if b["datetime"][:4] == year), None)
    return round((bars[-1]["close"] / first["close"] - 1) * 100, 2) if first else None


def analyze(data):
    bars = data["bars"]
    closes = [b["close"] for b in bars]
    s50, s200 = sma(closes, 50), sma(closes, 200)
    hi = max(closes[-252:]) if closes else None
    lo = min(closes[-252:]) if closes else None
    return {
        "label": data["label"],
        "symbol": data["symbol"],
        "asof": bars[-1]["datetime"],
        "close": closes[-1],
        "pct_1d": pct(closes, 1),
        "pct_5d": pct(closes, 5),
        "pct_1m": pct(closes, 21),
        "pct_ytd": ytd(bars),
        "sma20": sma(closes, 20),
        "sma50": s50,
        "sma200": s200,
        "above_sma200": (closes[-1] > s200) if s200 else None,
        "rsi14": rsi(closes),
        "atr14": atr(bars),
        "high_52w": round(hi, 4) if hi else None,
        "low_52w": round(lo, 4) if lo else None,
        # golden cross: 50 above 200. death cross: 50 below 200. None until both exist.
        "cross": ("golden" if s50 > s200 else "death") if (s50 and s200) else None,
    }


def latest_dir():
    dirs = sorted(glob.glob(os.path.join(VAULT, ".raw", "market-data", "*")))
    if not dirs:
        sys.exit("no market-data directories found — run fetch-market.py first")
    return dirs[-1]


def main(argv):
    d = argv[0] if argv else None
    outdir = os.path.join(VAULT, ".raw", "market-data", d) if d else latest_dir()
    files = [f for f in glob.glob(os.path.join(outdir, "*.json"))
             if not f.endswith(".analysis.json")]
    if not files:
        sys.exit(f"no data files in {outdir}")
    for f in sorted(files):
        data = json.load(open(f))
        a = analyze(data)
        with open(f.replace(".json", ".analysis.json"), "w") as out:
            json.dump(a, out, indent=2)
        print(f"{a['label']:8} close={a['close']:>12} 1d={a['pct_1d']:>6}% "
              f"rsi={a['rsi14']} sma200={'>' if a['above_sma200'] else '<'} {a['cross']}")
    print(f"Analyzed {len(files)} symbols in {outdir}")


def selfcheck():
    # Known-answer RSI: 14 up-moves then... classic Wilder example uses mixed; here a
    # monotonic rise gives RSI=100 (avg_loss=0), a monotonic fall gives RSI near 0.
    up = [float(i) for i in range(1, 30)]
    assert rsi(up) == 100.0, f"all-up RSI should be 100, got {rsi(up)}"
    down = [float(i) for i in range(30, 1, -1)]
    assert rsi(down) == 0.0 or rsi(down) < 1, f"all-down RSI ~0, got {rsi(down)}"
    # SMA
    assert sma([2, 4, 6, 8], 2) == 7.0, sma([2, 4, 6, 8], 2)
    assert sma([1, 2], 5) is None
    # pct
    assert pct([100, 110], 1) == 10.0
    # ATR: single 1-wide range every bar -> ATR=1
    bars = [{"high": 2, "low": 1, "close": 1.5} for _ in range(20)]
    assert atr(bars) == 1.0, atr(bars)
    # cross via analyze(): rising series -> sma50 > sma200 -> golden
    rising = {"label": "T", "symbol": "T",
              "bars": [{"datetime": f"2026-01-{(i % 28)+1:02d}", "open": i, "high": i + 1,
                        "low": i - 1, "close": float(i)} for i in range(1, 260)]}
    a = analyze(rising)
    assert a["cross"] == "golden", a["cross"]
    assert a["above_sma200"] is True
    print("selfcheck OK")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    else:
        main([x for x in sys.argv[1:] if not x.startswith("--")])
