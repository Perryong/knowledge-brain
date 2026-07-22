#!/usr/bin/env python3
"""Fetch daily market data from Twelve Data into .raw/market-data/YYYY-MM-DD/.

Stdlib only. Reads TWELVEDATA_API_KEY from the environment (never a tracked file).
Free tier: 8 req/min, 800/day, no indices — index exposure via ETF proxies.

Usage:
  TWELVEDATA_API_KEY=... python3 scripts/fetch-market.py          # fetch all
  python3 scripts/fetch-market.py --selfcheck                     # offline test, no key
"""
import json, os, ssl, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone


def _ssl_ctx():
    # ponytail: python.org macOS builds ship no CA bundle; use the system one at
    # /etc/ssl/cert.pem when present, else the platform default (fine on Linux).
    if os.path.exists("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


CTX = _ssl_ctx()

# label -> Twelve Data symbol. Indices are paid, so SPY/EWH are free ETF proxies.
SYMBOLS = {
    "SPY":     "SPY",      # S&P 500 proxy
    "EWH":     "EWH",      # Hang Seng proxy (iShares MSCI Hong Kong) — NOT literally HSI
    "NVDA":    "NVDA",
    "MSFT":    "MSFT",
    "XAUUSD":  "XAU/USD",  # gold
    "BTCUSD":  "BTC/USD",
}
OUTPUTSIZE = 250          # ~1 trading year, enough for SMA200
BASE = "https://api.twelvedata.com/time_series"
VAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fetch(symbol, key):
    """Return parsed Twelve Data time_series JSON, retrying once on rate-limit."""
    q = urllib.parse.urlencode(
        {"symbol": symbol, "interval": "1day", "outputsize": OUTPUTSIZE, "apikey": key}
    )
    for attempt in (1, 2):
        with urllib.request.urlopen(f"{BASE}?{q}", timeout=20, context=CTX) as r:
            d = json.load(r)
        if d.get("code") == 429 and attempt == 1:
            time.sleep(61)   # free tier: per-minute credit window
            continue
        return d
    return d


def normalize(label, symbol, raw):
    """Flatten Twelve Data response to bars sorted oldest->newest. Raises on error payload."""
    if raw.get("status") == "error" or "code" in raw:
        raise RuntimeError(f"{label}: {raw.get('code')} {raw.get('message')}")
    values = raw["values"]  # Twelve Data returns newest-first
    bars = [
        {k: (float(v[k]) if k != "datetime" else v[k])
         for k in ("datetime", "open", "high", "low", "close")
         if k in v}
        for v in reversed(values)
    ]
    return {
        "label": label,
        "symbol": symbol,
        "exchange": raw.get("meta", {}).get("exchange"),
        "currency": raw.get("meta", {}).get("currency"),
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bars": bars,
    }


def main():
    key = os.environ.get("TWELVEDATA_API_KEY")
    if not key:
        sys.exit("TWELVEDATA_API_KEY not set in environment")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = os.path.join(VAULT, ".raw", "market-data", day)
    os.makedirs(outdir, exist_ok=True)

    failed = []
    for i, (label, symbol) in enumerate(SYMBOLS.items()):
        try:
            data = normalize(label, symbol, fetch(symbol, key))
            path = os.path.join(outdir, f"{label}.json")
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            print(f"OK  {label:8} {len(data['bars'])} bars -> {path}")
        except Exception as e:
            print(f"ERR {label:8} {e}", file=sys.stderr)
            failed.append(label)
        if i < len(SYMBOLS) - 1:
            time.sleep(2)   # stay clear of the 8/min ceiling
    if failed:
        sys.exit(f"{len(failed)} symbol(s) failed: {', '.join(failed)}")
    print(f"All {len(SYMBOLS)} symbols written to {outdir}")


def selfcheck():
    """Offline: normalize() must sort newest-first input into oldest-first bars, and raise on errors."""
    raw = {
        "meta": {"exchange": "NYSE", "currency": "USD"},
        "values": [
            {"datetime": "2026-07-22", "open": "1", "high": "2", "low": "0.5", "close": "1.5"},
            {"datetime": "2026-07-21", "open": "0.9", "high": "1.1", "low": "0.8", "close": "1.0"},
        ],
    }
    out = normalize("TEST", "TEST", raw)
    assert out["bars"][0]["datetime"] == "2026-07-21", "bars must be oldest-first"
    assert out["bars"][-1]["close"] == 1.5, "latest close must be a float"
    assert out["currency"] == "USD"
    try:
        normalize("X", "X", {"code": 404, "message": "gated"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("error payload must raise")
    print("selfcheck OK")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    else:
        main()
