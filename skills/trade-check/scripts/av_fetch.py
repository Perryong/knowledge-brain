#!/usr/bin/env python3
"""
trade-check :: Alpha Vantage fetcher

Pulls the raw inputs the vault's 5-point Investment Entry Checklist needs for
ONE ticker and emits a normalised ``trade-check.metrics.v1`` JSON document.

Data-honesty contract (mirrors the skill):
  * Every field may be ``null``. Anything Alpha Vantage does not return stays
    null and is listed under ``missing`` -- it is never estimated, interpolated,
    or carried over from an older session.
  * Raw API payloads are cached to disk unchanged so any scorecard can be
    re-derived and audited later.
  * This script computes; it does not judge. Scoring lives in check_rules.py.

Stdlib only -- no pip installs required.

Usage
-----
    export ALPHAVANTAGE_API_KEY=...
    python3 av_fetch.py NVDA --out /tmp/NVDA.metrics.json

    # re-normalise from cached payloads without touching the network
    python3 av_fetch.py NVDA --offline

API calls per ticker: 3 (OVERVIEW, TIME_SERIES_DAILY, TIME_SERIES_INTRADAY).
The free tier is 25 requests/day, so caching is on by default.

If TIINGO_API_KEY is set, any call Alpha Vantage fails (quota, outage, missing
key) falls back to the Tiingo equivalent, converted into the same payload
shapes. See references/alpha-vantage.md for what the fallback can and cannot
supply.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "trade-check.metrics.v1"
BASE_URL = "https://www.alphavantage.co/query"
DEFAULT_CACHE = Path(os.environ.get("TRADE_CHECK_CACHE", Path.home() / ".cache" / "trade-check" / "alphavantage"))

# Sentinels Alpha Vantage uses for "we don't have this".
NULLISH = {"", "-", "none", "nan", "n/a", "null"}


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def num(value):
    """Parse to float, or None. Never guesses."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text.lower() in NULLISH:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def pe(value):
    """P/E specifically: Alpha Vantage returns 0 or a negative for unavailable."""
    parsed = num(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def pct(part, whole):
    if part is None or whole in (None, 0):
        return None
    return (part / whole - 1.0) * 100.0


def rounded(value, places=4):
    return None if value is None else round(value, places)


def mean(values):
    return sum(values) / len(values) if values else None


def ema(closes_asc, span):
    """Exponential moving average over the full ascending close history (pandas adjust=False)."""
    if len(closes_asc) < span:
        return None
    k = 2.0 / (span + 1)
    val = closes_asc[0]
    for c in closes_asc[1:]:
        val = c * k + val * (1 - k)
    return val


def sma(closes_asc, window, offset=0):
    """Simple moving average ending ``offset`` sessions before the latest bar."""
    end = len(closes_asc) - offset
    start = end - window
    if start < 0 or end <= 0:
        return None
    return mean(closes_asc[start:end])


# --------------------------------------------------------------------------
# transport + cache
# --------------------------------------------------------------------------
class FetchError(RuntimeError):
    pass


def ssl_context():
    """Default context, but fall back to the OS bundle when the Python build
    ships no CA store (python.org macOS installs). Verification stays ON."""
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats()["x509_ca"] == 0:
        for bundle in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
            if Path(bundle).is_file():
                ctx.load_verify_locations(bundle)
                break
    return ctx


def http_json(url: str, timeout: int, provider: str):
    request = urllib.request.Request(url, headers={"User-Agent": "trade-check/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError as exc:
        raise FetchError(f"network error reaching {provider}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise FetchError(f"{provider} returned a non-JSON body") from exc


def cache_path(cache_dir: Path, symbol: str, function: str, suffix: str = "") -> Path:
    name = function + (f"_{suffix}" if suffix else "")
    return cache_dir / symbol.upper() / f"{name}.json"


def read_cache(path: Path, ttl_seconds: int, offline: bool):
    if not path.is_file():
        return None
    try:
        wrapper = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if offline:
        return wrapper
    if ttl_seconds <= 0:
        return None
    age = time.time() - wrapper.get("_fetched_at_epoch", 0)
    return wrapper if age <= ttl_seconds else None


def write_cache(path: Path, wrapper: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(wrapper, indent=2, sort_keys=True))


def call_api(params: dict, api_key: str, timeout: int) -> dict:
    query = dict(params)
    query["apikey"] = api_key
    url = f"{BASE_URL}?{urllib.parse.urlencode(query)}"
    try:
        payload = http_json(url, timeout, "Alpha Vantage")
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} from Alpha Vantage for {params.get('function')}") from exc

    # Alpha Vantage signals problems inside a 200 response.
    for key in ("Error Message", "Note", "Information"):
        if key in payload:
            raise FetchError(f"Alpha Vantage {key}: {str(payload[key])[:400]}")
    if not payload:
        raise FetchError("Alpha Vantage returned an empty object")
    return payload


def get(function: str, symbol: str, api_key: str, cfg, extra: dict | None = None, suffix: str = ""):
    """Cached fetch. Returns (payload, provenance) or (None, provenance) on failure."""
    path = cache_path(cfg.cache_dir, symbol, function, suffix)
    cached = read_cache(path, cfg.cache_ttl, cfg.offline)
    if cached is not None:
        return cached["payload"], {
            "function": function,
            "origin": "cache",
            "fetched_at_utc": cached.get("_fetched_at_utc"),
            "path": str(path),
        }
    if cfg.offline:
        return None, {"function": function, "origin": "offline-miss", "error": f"no cached payload at {path}"}
    if not api_key:
        return None, {"function": function, "origin": "error", "error": "no API key (set ALPHAVANTAGE_API_KEY)"}

    params = {"function": function, "symbol": symbol}
    params.update(extra or {})
    try:
        payload = call_api(params, api_key, cfg.timeout)
    except FetchError as exc:
        return None, {"function": function, "origin": "error", "error": str(exc)}

    now = datetime.now(timezone.utc)
    wrapper = {
        "_fetched_at_utc": now.isoformat(timespec="seconds"),
        "_fetched_at_epoch": now.timestamp(),
        "_params": {k: v for k, v in params.items() if k != "apikey"},
        "payload": payload,
    }
    write_cache(path, wrapper)
    time.sleep(cfg.sleep)
    return payload, {
        "function": function,
        "origin": "api",
        "fetched_at_utc": wrapper["_fetched_at_utc"],
        "path": str(path),
    }


# --------------------------------------------------------------------------
# Tiingo fallback
#
# When an Alpha Vantage call fails (quota, network, missing key), the same
# input can usually be rebuilt from Tiingo. Tiingo responses are cached raw,
# then converted into the Alpha Vantage payload shapes so the rest of the
# pipeline stays provider-agnostic. Known gaps stay honest:
#   * Tiingo has no forward P/E on any tier -> rule 2 input stays null.
#   * Free-tier fundamentals are Dow-30 only -> most tickers error, stay null.
#   * Shares outstanding is derived from marketCap / close and labelled so.
#   * Daily prices use Tiingo's adjusted fields (a bonus: AV free is unadjusted).
# --------------------------------------------------------------------------
TIINGO_BASE = "https://api.tiingo.com"


def tiingo_call(path: str, params: dict, token: str, timeout: int):
    query = dict(params)
    query["token"] = token
    url = f"{TIINGO_BASE}{path}?{urllib.parse.urlencode(query)}"
    try:
        payload = http_json(url, timeout, "Tiingo")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail", "")[:200]
        except Exception:
            pass
        raise FetchError(f"HTTP {exc.code} from Tiingo for {path}: {detail}") from exc
    if isinstance(payload, dict) and payload.get("detail"):
        raise FetchError(f"Tiingo: {str(payload['detail'])[:200]}")
    if not payload:
        raise FetchError("Tiingo returned an empty body")
    return payload


TIINGO_ENDPOINTS = {
    "TIINGO_DAILY": lambda symbol, cfg: (
        f"/tiingo/daily/{symbol}/prices",
        {"startDate": (datetime.now(timezone.utc).date() - timedelta(days=450)).isoformat()},
    ),
    "TIINGO_INTRADAY": lambda symbol, cfg: (
        f"/iex/{symbol}/prices",
        {"resampleFreq": cfg.interval, "columns": "open,high,low,close,volume"},
    ),
    "TIINGO_FUNDAMENTALS": lambda symbol, cfg: (f"/tiingo/fundamentals/{symbol}/daily", {}),
}


def tiingo_get(kind: str, symbol: str, token: str, cfg, suffix: str = ""):
    """Cached Tiingo fetch, mirroring get(). Returns (raw_payload, provenance)."""
    path = cache_path(cfg.cache_dir, symbol, kind, suffix)
    cached = read_cache(path, cfg.cache_ttl, cfg.offline)
    if cached is not None:
        return cached["payload"], {
            "function": kind,
            "origin": "cache",
            "fetched_at_utc": cached.get("_fetched_at_utc"),
            "path": str(path),
        }
    if cfg.offline:
        return None, {"function": kind, "origin": "offline-miss", "error": f"no cached payload at {path}"}
    if not token:
        return None, {"function": kind, "origin": "error", "error": "no API key (set TIINGO_API_KEY)"}

    url_path, params = TIINGO_ENDPOINTS[kind](symbol, cfg)
    try:
        payload = tiingo_call(url_path, params, token, cfg.timeout)
    except FetchError as exc:
        return None, {"function": kind, "origin": "error", "error": str(exc)}

    now = datetime.now(timezone.utc)
    wrapper = {
        "_fetched_at_utc": now.isoformat(timespec="seconds"),
        "_fetched_at_epoch": now.timestamp(),
        "_params": {"path": url_path, **params},
        "payload": payload,
    }
    write_cache(path, wrapper)
    return payload, {
        "function": kind,
        "origin": "api",
        "fetched_at_utc": wrapper["_fetched_at_utc"],
        "path": str(path),
    }


def tiingo_daily_to_av(payload):
    """Tiingo daily rows -> Alpha Vantage TIME_SERIES_DAILY shape (adjusted)."""
    if not isinstance(payload, list):
        return None
    series = {}
    for row in payload:
        stamp = str(row.get("date", ""))[:10]
        if not stamp:
            continue
        series[stamp] = {
            "1. open": row.get("adjOpen", row.get("open")),
            "2. high": row.get("adjHigh", row.get("high")),
            "3. low": row.get("adjLow", row.get("low")),
            "4. close": row.get("adjClose", row.get("close")),
            "6. volume": row.get("adjVolume", row.get("volume")),
        }
    return {"Meta Data": {"2. Symbol": "tiingo-fallback"}, "Time Series (Daily)": series} if series else None


def tiingo_intraday_to_av(payload, interval):
    """Tiingo IEX bars -> Alpha Vantage TIME_SERIES_INTRADAY shape."""
    if not isinstance(payload, list):
        return None
    series = {}
    for row in payload:
        stamp = str(row.get("date", "")).replace("T", " ")[:19]
        if len(stamp) < 19:
            continue
        series[stamp] = {
            "1. open": row.get("open"),
            "2. high": row.get("high"),
            "3. low": row.get("low"),
            "4. close": row.get("close"),
            "5. volume": row.get("volume"),
        }
    return {"Meta Data": {"2. Symbol": "tiingo-fallback"}, f"Time Series ({interval})": series} if series else None


def tiingo_fundamentals_to_av(payload, last_close):
    """Tiingo daily fundamentals -> partial OVERVIEW. Forward P/E does not exist
    on Tiingo and stays unavailable; shares outstanding is derived."""
    row = payload[-1] if isinstance(payload, list) and payload else None
    if not isinstance(row, dict):
        return None
    market_cap = num(row.get("marketCap"))
    shares = market_cap / last_close if market_cap and last_close else None
    return {
        "TrailingPE": row.get("peRatio"),
        "ForwardPE": "0",  # sentinel: unavailable, parses to null
        "MarketCapitalization": market_cap,
        "SharesOutstanding": None if shares is None else str(int(shares)),
        "LatestQuarter": str(row.get("date", ""))[:10] or None,
    }


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------
def parse_daily(payload):
    """-> list of bars ascending by date, each {date, open, high, low, close, volume}."""
    series = None
    for key in payload:
        if key.lower().startswith("time series"):
            series = payload[key]
            break
    if not isinstance(series, dict):
        return []
    bars = []
    for date, row in series.items():
        bar = {
            "date": date,
            "open": num(row.get("1. open")),
            "high": num(row.get("2. high")),
            "low": num(row.get("3. low")),
            "close": num(row.get("4. close")),
            "volume": num(row.get("6. volume") or row.get("5. volume")),
        }
        if bar["close"] is not None:
            bars.append(bar)
    bars.sort(key=lambda b: b["date"])
    return bars


def parse_intraday(payload):
    series = None
    for key in payload:
        if key.lower().startswith("time series"):
            series = payload[key]
            break
    if not isinstance(series, dict):
        return []
    bars = []
    for stamp, row in series.items():
        bar = {
            "stamp": stamp,
            "high": num(row.get("2. high")),
            "low": num(row.get("3. low")),
            "close": num(row.get("4. close")),
            "volume": num(row.get("5. volume")),
        }
        if None not in (bar["high"], bar["low"], bar["close"], bar["volume"]):
            bars.append(bar)
    bars.sort(key=lambda b: b["stamp"])
    return bars


def candle_shape(bar):
    """Body/wick geometry as a share of the session range."""
    out = {
        "date": bar["date"],
        "open": rounded(bar["open"], 4),
        "high": rounded(bar["high"], 4),
        "low": rounded(bar["low"], 4),
        "close": rounded(bar["close"], 4),
        "color": None,
        "body_pct_of_range": None,
        "upper_wick_pct_of_range": None,
        "lower_wick_pct_of_range": None,
    }
    o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
    if None in (o, h, l, c):
        return out
    out["color"] = "green" if c > o else "red" if c < o else "doji"
    span = h - l
    if span <= 0:
        return out
    out["body_pct_of_range"] = rounded(abs(c - o) / span * 100, 2)
    out["upper_wick_pct_of_range"] = rounded((h - max(o, c)) / span * 100, 2)
    out["lower_wick_pct_of_range"] = rounded((min(o, c) - l) / span * 100, 2)
    return out


def session_vwap(bars, slope_lookback_bars):
    """Cumulative VWAP over the most recent intraday session only."""
    result = {
        "value": None,
        "session_date": None,
        "bars_used": 0,
        "session_close": None,
        "session_low": None,
        "close_vs_vwap_pct": None,
        "traded_below_vwap_intraday": None,
        "reclaimed_vwap": None,
        "slope_pct_recent": None,
    }
    if not bars:
        return result
    last_day = bars[-1]["stamp"][:10]
    day_bars = [b for b in bars if b["stamp"][:10] == last_day]
    if not day_bars:
        return result

    cum_pv = 0.0
    cum_v = 0.0
    running = []
    for bar in day_bars:
        typical = (bar["high"] + bar["low"] + bar["close"]) / 3.0
        cum_pv += typical * bar["volume"]
        cum_v += bar["volume"]
        running.append(cum_pv / cum_v if cum_v else None)

    if not cum_v:
        return result

    vwap = cum_pv / cum_v
    close = day_bars[-1]["close"]
    low = min(b["low"] for b in day_bars)

    result.update(
        {
            "value": rounded(vwap, 4),
            "session_date": last_day,
            "bars_used": len(day_bars),
            "session_close": rounded(close, 4),
            "session_low": rounded(low, 4),
            "close_vs_vwap_pct": rounded(pct(close, vwap), 3),
            "traded_below_vwap_intraday": bool(low < vwap),
            "reclaimed_vwap": bool(low < vwap and close > vwap),
        }
    )
    if len(running) > slope_lookback_bars and running[-1 - slope_lookback_bars]:
        result["slope_pct_recent"] = rounded(pct(running[-1], running[-1 - slope_lookback_bars]), 3)
    return result


def build_metrics(symbol, overview, daily_payload, intraday_payload, sources, cfg):
    missing = []
    warnings = []

    metrics = {
        "schema": SCHEMA,
        "symbol": symbol.upper(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_source": "alphavantage",
        "sources": sources,
        "company": {},
        "fundamentals": {},
        "price": {},
        "moving_averages": {},
        "candle": {},
        "volume": {},
        "vwap": {},
        "warnings": warnings,
        "missing": missing,
    }

    # ---- fundamentals ----------------------------------------------------
    if overview:
        metrics["company"] = {
            "name": overview.get("Name"),
            "sector": overview.get("Sector"),
            "industry": overview.get("Industry"),
            "currency": overview.get("Currency"),
            "latest_quarter": overview.get("LatestQuarter"),
        }
        pe_ttm = pe(overview.get("TrailingPE")) or pe(overview.get("PERatio"))
        metrics["fundamentals"] = {
            "pe_ttm": rounded(pe_ttm, 3),
            "pe_forward": rounded(pe(overview.get("ForwardPE")), 3),
            "peg_ratio": rounded(num(overview.get("PEGRatio")), 3),
            "eps_ttm": rounded(num(overview.get("EPS")), 4),
            "profit_margin": rounded(num(overview.get("ProfitMargin")), 4),
            "quarterly_earnings_growth_yoy": rounded(num(overview.get("QuarterlyEarningsGrowthYOY")), 4),
            "quarterly_revenue_growth_yoy": rounded(num(overview.get("QuarterlyRevenueGrowthYOY")), 4),
            "shares_outstanding": num(overview.get("SharesOutstanding")),
            "market_cap": num(overview.get("MarketCapitalization")),
        }
        for field in ("pe_ttm", "pe_forward", "shares_outstanding"):
            if metrics["fundamentals"].get(field) is None:
                missing.append(f"fundamentals.{field}")
        if metrics["fundamentals"].get("pe_ttm") is None:
            warnings.append(
                "No positive TTM P/E from Alpha Vantage. The company may be loss-making or "
                "earnings distorted -- the vault's P/E page says to use revenue growth, cash "
                "flow, or margins instead. Rule 2 stays unknown."
            )
    else:
        missing.extend(["fundamentals.pe_ttm", "fundamentals.pe_forward", "fundamentals.shares_outstanding"])

    # ---- daily series ----------------------------------------------------
    bars = parse_daily(daily_payload) if daily_payload else []
    if not bars:
        missing.extend(["price.close", "moving_averages.*", "candle.*", "volume.*"])
        warnings.append("No daily series returned; trend, candle, and volume rules cannot be scored.")
        return metrics

    closes = [b["close"] for b in bars]
    volumes = [b["volume"] for b in bars if b["volume"] is not None]
    last = bars[-1]

    metrics["price"] = {
        "close": rounded(last["close"], 4),
        "session_date": last["date"],
        "sessions_available": len(bars),
        "prev_close": rounded(bars[-2]["close"], 4) if len(bars) > 1 else None,
    }

    mas = {}
    for window in (10, 20, 30, 50, 200):
        mas[f"ma{window}"] = rounded(sma(closes, window), 4)
        if mas[f"ma{window}"] is None:
            missing.append(f"moving_averages.ma{window}")
    for window, lookback in ((30, cfg.slope_lookback), (200, 20), (10, 5)):
        now_val = sma(closes, window)
        then_val = sma(closes, window, offset=lookback)
        mas[f"ma{window}_slope_pct_{lookback}d"] = rounded(pct(now_val, then_val), 3)
    mas["price_vs_ma10_pct"] = rounded(pct(last["close"], mas["ma10"]), 3)
    mas["price_vs_ma30_pct"] = rounded(pct(last["close"], mas["ma30"]), 3)
    mas["price_vs_ma50_pct"] = rounded(pct(last["close"], mas["ma50"]), 3)
    mas["price_vs_ma200_pct"] = rounded(pct(last["close"], mas["ma200"]), 3)
    if mas["ma10"] is not None and mas["ma30"] is not None:
        mas["ma10_above_ma30"] = bool(mas["ma10"] > mas["ma30"])
    else:
        mas["ma10_above_ma30"] = None
    # swing-trend pair used by the backtest template (bt_prepare.py --trend ema)
    mas["ema12"] = rounded(ema(closes, 12), 4)
    mas["ema21"] = rounded(ema(closes, 21), 4)
    mas["price_vs_ema21_pct"] = rounded(pct(last["close"], mas["ema21"]), 3)
    mas["ema12_above_ema21"] = (bool(mas["ema12"] > mas["ema21"])
                                if mas["ema12"] is not None and mas["ema21"] is not None else None)
    metrics["moving_averages"] = mas

    if len(bars) < 200:
        warnings.append(
            f"Only {len(bars)} daily sessions available; MA200 (and therefore rule 3) may be unavailable. "
            "Re-run with --outputsize full."
        )

    metrics["candle"] = candle_shape(last)

    avg_window = cfg.volume_window
    prior = [b["volume"] for b in bars[-(avg_window + 1):-1] if b["volume"] is not None]
    avg_vol = mean(prior) if len(prior) == avg_window else None
    today_vol = last["volume"]
    shares = metrics.get("fundamentals", {}).get("shares_outstanding")
    metrics["volume"] = {
        "volume": today_vol,
        "avg_volume_window_sessions": avg_window,
        "avg_volume": rounded(avg_vol, 1),
        "volume_ratio": rounded(today_vol / avg_vol, 3) if today_vol and avg_vol else None,
        "turnover_pct": rounded(today_vol / shares * 100, 4) if today_vol and shares else None,
        "shares_outstanding": shares,
    }
    if metrics["volume"]["volume_ratio"] is None:
        missing.append("volume.volume_ratio")
    if metrics["volume"]["turnover_pct"] is None:
        missing.append("volume.turnover_pct")
        warnings.append(
            "Turnover % needs shares outstanding, which OVERVIEW did not supply. "
            "Supply it manually or leave rule 5's institutional test unknown."
        )
    if len(volumes) >= 2 and bars[-2]["volume"]:
        metrics["volume"]["volume_vs_prev_session_pct"] = rounded(pct(today_vol, bars[-2]["volume"]), 2)

    # ---- VWAP ------------------------------------------------------------
    intraday_bars = parse_intraday(intraday_payload) if intraday_payload else []
    metrics["vwap"] = session_vwap(intraday_bars, cfg.vwap_slope_bars)
    metrics["vwap"]["interval"] = cfg.interval
    if metrics["vwap"]["value"] is None:
        missing.append("vwap.value")
        warnings.append("No intraday series; VWAP (rule 4) cannot be scored from this data.")
    elif metrics["vwap"]["session_date"] != last["date"]:
        warnings.append(
            f"VWAP session ({metrics['vwap']['session_date']}) differs from the latest daily bar "
            f"({last['date']}). Rule 4 is judged on the intraday session's own close."
        )
    return metrics


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch Alpha Vantage data for one ticker and emit trade-check metrics.")
    parser.add_argument("symbol")
    parser.add_argument("--api-key", default=os.environ.get("ALPHAVANTAGE_API_KEY", ""))
    parser.add_argument("--tiingo-key", default=os.environ.get("TIINGO_API_KEY", ""),
                        help="enables the Tiingo fallback when an Alpha Vantage call fails")
    parser.add_argument("--out", help="write metrics JSON here (default: stdout)")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--cache-ttl", type=int, default=3600, help="seconds; 0 forces a refetch")
    parser.add_argument("--offline", action="store_true", help="use cached payloads only, never call the API")
    parser.add_argument("--interval", default="5min", choices=["1min", "5min", "15min", "30min", "60min"])
    parser.add_argument("--outputsize", default="full", choices=["compact", "full"])
    parser.add_argument("--extended-hours", default="false", choices=["true", "false"])
    parser.add_argument("--volume-window", type=int, default=20, help="sessions in the average-volume baseline")
    parser.add_argument("--slope-lookback", type=int, default=5, help="sessions used for the MA30 slope")
    parser.add_argument("--vwap-slope-bars", type=int, default=12, help="intraday bars used for the VWAP slope")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep", type=float, default=1.0, help="seconds between live API calls")
    parser.add_argument("--skip-intraday", action="store_true", help="save a call; leaves VWAP unknown")
    cfg = parser.parse_args(argv)

    symbol = cfg.symbol.upper()
    sources = []

    overview, prov = get("OVERVIEW", symbol, cfg.api_key, cfg)
    sources.append(prov)

    daily, prov = get(
        "TIME_SERIES_DAILY", symbol, cfg.api_key, cfg,
        extra={"outputsize": cfg.outputsize}, suffix=cfg.outputsize,
    )
    sources.append(prov)

    intraday = None
    if cfg.skip_intraday:
        sources.append({"function": "TIME_SERIES_INTRADAY", "origin": "skipped"})
    else:
        intraday, prov = get(
            "TIME_SERIES_INTRADAY", symbol, cfg.api_key, cfg,
            extra={"interval": cfg.interval, "outputsize": "compact", "extended_hours": cfg.extended_hours},
            suffix=cfg.interval,
        )
        sources.append(prov)

    # ---- Tiingo fallback for whatever Alpha Vantage could not supply ------
    tiingo_enabled = bool(cfg.tiingo_key) or cfg.offline
    if tiingo_enabled and daily is None:
        raw, prov = tiingo_get("TIINGO_DAILY", symbol, cfg.tiingo_key, cfg)
        converted = tiingo_daily_to_av(raw) if raw else None
        if converted:
            daily = converted
            prov["note"] = "fallback for TIME_SERIES_DAILY (adjusted prices)"
        sources.append(prov)
    if tiingo_enabled and intraday is None and not cfg.skip_intraday:
        raw, prov = tiingo_get("TIINGO_INTRADAY", symbol, cfg.tiingo_key, cfg, suffix=cfg.interval)
        converted = tiingo_intraday_to_av(raw, cfg.interval) if raw else None
        if converted:
            intraday = converted
            prov["note"] = "fallback for TIME_SERIES_INTRADAY (IEX feed)"
        sources.append(prov)
    if tiingo_enabled and overview is None:
        raw, prov = tiingo_get("TIINGO_FUNDAMENTALS", symbol, cfg.tiingo_key, cfg)
        bars = parse_daily(daily) if daily else []
        last_close = bars[-1]["close"] if bars else None
        converted = tiingo_fundamentals_to_av(raw, last_close) if raw else None
        if converted:
            overview = converted
            prov["note"] = "fallback for OVERVIEW (no forward P/E on Tiingo; shares derived from marketCap/close)"
        sources.append(prov)

    metrics = build_metrics(symbol, overview, daily, intraday, sources, cfg)

    if any(s.get("function") == "TIINGO_FUNDAMENTALS" and s.get("note") for s in sources):
        metrics["warnings"].append(
            "Fundamentals came from the Tiingo fallback: forward P/E is not offered by Tiingo "
            "(rule 2 needs a user-supplied figure) and shares outstanding is derived from "
            "marketCap / close, not reported directly."
        )

    for source in sources:
        if source.get("error"):
            metrics["warnings"].append(f"{source['function']}: {source['error']}")

    text = json.dumps(metrics, indent=2)
    if cfg.out:
        Path(cfg.out).parent.mkdir(parents=True, exist_ok=True)
        Path(cfg.out).write_text(text)
        print(f"wrote {cfg.out}", file=sys.stderr)
    else:
        print(text)

    if metrics["missing"]:
        print(f"missing inputs: {', '.join(sorted(set(metrics['missing'])))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())