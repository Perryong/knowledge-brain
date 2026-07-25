#!/usr/bin/env python3
"""Render analysis JSON into wiki pages. Deterministic, idempotent, no network/LLM.

Reads .raw/market-data/YYYY-MM-DD/*.analysis.json and writes:
  wiki/sources/market-data/YYYY-MM-DD.md   daily snapshot (overwritten)
  wiki/entities/markets/<LABEL>.md         evergreen per-instrument, history row upserted
  wiki/log.md                              one log entry per day (upserted)

Re-running the same day is a no-op on counts (rows keyed by date). Numbers are
computed and trustworthy; the narrative layer (autoresearch, Phase 4) is separate.

Usage:
  python3 scripts/render-market.py [YYYY-MM-DD]
  python3 scripts/render-market.py --selfcheck
"""
import glob, json, os, re, sys

VAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# label -> (display title, region, asset class) for page metadata
META = {
    "SPY":    ("SPY — S&P 500 ETF (proxy)", "US", "equity-index-proxy"),
    "EWH":    ("EWH — iShares MSCI Hong Kong (Hang Seng proxy)", "HK", "equity-index-proxy"),
    "NVDA":   ("NVDA — NVIDIA", "US", "equity"),
    "MSFT":   ("MSFT — Microsoft", "US", "equity"),
    "XAUUSD": ("Gold (XAU/USD)", "Global", "commodity"),
    "BTCUSD": ("Bitcoin (BTC/USD)", "Global", "crypto"),
}
DISCLAIMER = ("> [!warning] Not investment advice\n"
              "> Indicator values are computed and deterministic. Any narrative in linked "
              "pages is model-generated synthesis and may be wrong. Do your own research.")
H_OPEN, H_CLOSE = "<!-- history:start -->", "<!-- history:end -->"


def _sign(x):
    return f"+{x}" if isinstance(x, (int, float)) and x >= 0 else f"{x}"


def daily_page(day, rows):
    lines = [f"| {r['label']} | {_sign(r['pct_1d'])}% | {r['close']} | {_sign(r['pct_ytd'])}% | "
             f"{r['rsi14']} | {'>' if r['above_sma200'] else '<'}SMA200 | {r['cross']} |"
             for r in rows]
    body = "\n".join(lines)
    links = " ".join(f"[[{r['label']}]]" for r in rows)
    return f"""---
type: source
title: "Market snapshot {day}"
updated: {day}
tags:
  - market
  - snapshot
status: dated
related:
{chr(10).join(f'  - "[[{r["label"]}]]"' for r in rows)}
---

# Market snapshot — {day}

{DISCLAIMER}

| Instrument | 1d | Close | YTD | RSI(14) | vs SMA200 | Cross |
|---|---|---|---|---|---|---|
{body}

Instruments: {links}

Narrative: [[Market Drivers {day}]] (filed by the autoresearch step; may not exist yet)

See also: [[_index|Entities]] · [[log]]
"""


def _history_rows(text):
    """Parse existing history table between markers -> {date: full_row_line}."""
    m = re.search(re.escape(H_OPEN) + r"(.*?)" + re.escape(H_CLOSE), text, re.S)
    rows = {}
    if m:
        for line in m.group(1).strip().splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 1 and re.match(r"\d{4}-\d{2}-\d{2}", cells[0]):
                rows[cells[0]] = line.strip()
    return rows


def entity_page(label, a):
    title, region, klass = META[label]
    day = a["asof"]
    path = os.path.join(VAULT, "wiki", "entities", "markets", f"{label}.md")
    existing = open(path).read() if os.path.exists(path) else ""
    rows = _history_rows(existing)
    rows[day] = (f"| {day} | {a['close']} | {_sign(a['pct_1d'])}% | {a['rsi14']} | "
                 f"{'>' if a['above_sma200'] else '<'}SMA200 | {a['cross']} |")
    hist = "\n".join(rows[d] for d in sorted(rows))
    return path, f"""---
type: entity
title: "{title}"
category: market-instrument
region: {region}
asset_class: {klass}
tags:
  - market
  - {klass}
status: evergreen
updated: {day}
related:
  - "[[Market snapshot {day}]]"
---

# {title}

Twelve Data symbol: `{a['symbol']}`. Region: {region}. Class: {klass}.

## Latest reading ({day})
- **Close** {a['close']} ({_sign(a['pct_1d'])}% 1d, {_sign(a['pct_5d'])}% 5d, {_sign(a['pct_ytd'])}% YTD)
- **Trend** {'above' if a['above_sma200'] else 'below'} SMA200 · {a['cross']} cross (SMA50 {a['sma50']} / SMA200 {a['sma200']})
- **RSI(14)** {a['rsi14']} · **ATR(14)** {a['atr14']}
- **52w** {a['low_52w']} – {a['high_52w']}

## History
{H_OPEN}
| Date | Close | 1d% | RSI | Trend | Cross |
|---|---|---|---|---|---|
{hist}
{H_CLOSE}
"""


def upsert_log(day, rows):
    path = os.path.join(VAULT, "wiki", "log.md")
    text = open(path).read() if os.path.exists(path) else "# Log\n"
    header = f"## [{day}] market | Market snapshot"
    entry = (f"{header}\n\n"
             f"- Type: market-data\n"
             f"- Location: wiki/sources/market-data/{day}.md\n"
             f"- Instruments: {', '.join(r['label'] for r in rows)}\n"
             f"- Source: Twelve Data (daily bars)\n")
    # replace an existing same-day market block, else prepend under the title line
    pat = re.compile(re.escape(header) + r".*?(?=\n## |\Z)", re.S)
    if pat.search(text):
        text = pat.sub(entry.rstrip() + "\n", text)
    else:
        # insert after the first line (title) so newest-ish stays near top
        parts = text.split("\n", 1)
        text = parts[0] + "\n\n" + entry + "\n" + (parts[1] if len(parts) > 1 else "")
    open(path, "w").write(text)


def render(day):
    d = os.path.join(VAULT, ".raw", "market-data", day)
    files = sorted(f for f in glob.glob(os.path.join(d, "*.analysis.json")))
    if not files:
        sys.exit(f"no analysis files in {d} — run analyze-market.py first")
    rows = [json.load(open(f)) for f in files]

    os.makedirs(os.path.join(VAULT, "wiki", "sources", "market-data"), exist_ok=True)
    os.makedirs(os.path.join(VAULT, "wiki", "entities", "markets"), exist_ok=True)

    open(os.path.join(VAULT, "wiki", "sources", "market-data", f"{day}.md"), "w").write(
        daily_page(day, rows))
    for a in rows:
        path, content = entity_page(a["label"], a)
        open(path, "w").write(content)
    upsert_log(day, rows)
    print(f"Rendered {len(rows)} instruments for {day}: daily page + entities + log")


def latest_day():
    dirs = sorted(glob.glob(os.path.join(VAULT, ".raw", "market-data", "*")))
    if not dirs:
        sys.exit("no market-data — run fetch-market.py")
    return os.path.basename(dirs[-1])


def selfcheck():
    import tempfile
    # history upsert must be idempotent and keyed by date
    txt = f"{H_OPEN}\n| Date | Close |\n|---|---|\n| 2026-07-20 | 100 |\n{H_CLOSE}"
    r = _history_rows(txt)
    assert set(r) == {"2026-07-20"}, r
    r["2026-07-20"] = "| 2026-07-20 | 999 |"   # same key -> replace, not add
    r["2026-07-21"] = "| 2026-07-21 | 101 |"
    assert len(r) == 2 and "999" in r["2026-07-20"]
    # daily_page renders a full row per instrument
    a = {"label": "NVDA", "pct_1d": 2.48, "close": 212.44, "pct_ytd": 12.49,
         "rsi14": 62.97, "above_sma200": True, "cross": "golden"}
    page = daily_page("2026-07-22", [a])
    assert "| NVDA | +2.48% | 212.44 |" in page and "Not investment advice" in page
    print("selfcheck OK")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    else:
        args = [x for x in sys.argv[1:] if not x.startswith("--")]
        render(args[0] if args else latest_day())
