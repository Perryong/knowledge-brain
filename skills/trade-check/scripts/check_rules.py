#!/usr/bin/env python3
"""
trade-check :: rule engine

Scores a ``trade-check.metrics.v1`` document against the vault's 5-point
Investment Entry Checklist and emits a scorecard (JSON, a markdown table, or
a ready-to-file vault page body).

Scoring contract:
  * Each rule is ``pass``, ``fail``, or ``unknown``. A missing input is
    ``unknown`` -- never a pass, never a quiet fail.
  * ``enter-candidate`` requires all five rules to pass.
  * Any hard fail (EMA12 below EMA21, forward P/E materially above TTM,
    or red candle on institutional volume) forces ``avoid``. A below-VWAP
    close is a single-session signal and stays a recoverable fail (wait).
  * Everything else is ``wait``.

Rule 1 (business makes sense) cannot be computed from market data. It is
``unknown`` unless a human passes --business pass|fail.

Thresholds default to the values in references/thresholds.json but the VAULT
PAGES ARE THE AUTHORITY. If a vault page disagrees, pass --thresholds with a
corrected file rather than editing this script.

Usage
-----
    python3 check_rules.py /tmp/NVDA.metrics.json --business pass --format both
    python3 av_fetch.py NVDA | python3 check_rules.py - --page-out review.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "trade-check.scorecard.v1"

DEFAULT_THRESHOLDS = {
    # Rule 2 -- Price-Earnings Ratio
    "pe_forward_tolerance_pct": 2.0,      # Fwd within +2% of TTM still counts as "≈ flat"
    "pe_hard_fail_pct": 10.0,             # Fwd more than 10% above TTM = valuation shock risk
    # Rule 3 -- Moving Averages
    "pullback_band_pct": 3.0,             # "at" EMA21 means within this band
    "ma200_safe_zone_pct": 20.0,          # MA200 zones are context notes only since the EMA rule (2026-08-24)
    "ma200_no_add_pct": 40.0,             # 20-40%: still bullish, do not add
    "ma200_trim_pct": 60.0,               # 40-60%: take partial profits; >60% distribution
    "ma30_safe_pct": 5.0,                 # 0-5% above MA30 = safe zone
    "ma30_caution_pct": 10.0,             # 5-10% caution; >10-12% stretched
    # Rule 4 -- VWAP
    "vwap_overextended_pct": 3.0,         # far above VWAP = chasing
    # Rule 5 -- Candle + Volume
    "volume_ratio_institutional": 1.5,
    "volume_ratio_moderate": 1.0,
    "turnover_pct_institutional": 1.0,
    "turnover_pct_quiet": 0.5,
    "long_lower_wick_pct": 40.0,          # lower wick as share of the session range
    "small_body_pct": 25.0,               # body as share of range = indecision
}

STATUS_ORDER = {"fail": 0, "unknown": 1, "pass": 2}


# --------------------------------------------------------------------------
def dig(data, *path):
    node = data
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def fmt(value, unit="", places=2):
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:,.{places}f}{unit}"
    return f"{value}{unit}"


def rule(rid, name, status, threshold, observed, notes, hard_fail=False):
    return {
        "id": rid,
        "name": name,
        "status": status,
        "threshold": threshold,
        "observed": observed,
        "hard_fail": bool(hard_fail and status == "fail"),
        "notes": notes,
    }


# --------------------------------------------------------------------------
# Rule 1 -- business makes sense
# --------------------------------------------------------------------------
def rule_business(metrics, business):
    notes = []
    company = metrics.get("company") or {}
    fundamentals = metrics.get("fundamentals") or {}
    if company.get("name"):
        notes.append(f"{company['name']} — {company.get('sector') or 'sector n/a'} / {company.get('industry') or 'industry n/a'}.")
    margin = fundamentals.get("profit_margin")
    rev_growth = fundamentals.get("quarterly_revenue_growth_yoy")
    if margin is not None:
        notes.append(f"Profit margin {margin * 100:.2f}%.")
    if rev_growth is not None:
        notes.append(f"Quarterly revenue growth YoY {rev_growth * 100:.2f}%.")
    notes.append("Context only — this rule is a human judgement and is never auto-passed.")

    status = business if business in ("pass", "fail") else "unknown"
    if status == "unknown":
        notes.append("No human verdict supplied (--business pass|fail), so this stays unknown.")
    return rule(
        1, "Business makes sense", status,
        "Human judgement: you can explain the business and why it earns money",
        "asserted: " + (business or "none"),
        notes,
    )


# --------------------------------------------------------------------------
# Rule 2 -- Forward P/E <= TTM P/E
# --------------------------------------------------------------------------
def rule_pe(metrics, T):
    ttm = dig(metrics, "fundamentals", "pe_ttm")
    fwd = dig(metrics, "fundamentals", "pe_forward")
    threshold = "Forward P/E ≤ TTM P/E"
    observed = f"TTM {fmt(ttm)} / Forward {fmt(fwd)}"
    notes = []

    if ttm is None or fwd is None:
        if ttm is None:
            notes.append("No positive TTM P/E — company may be loss-making or earnings distorted. "
                         "The vault's P/E page says to fall back to revenue growth, cash flow, or margins.")
        if fwd is None:
            notes.append("No forward P/E from the data source; supply an analyst estimate manually or leave unknown.")
        return rule(2, "Forward P/E ≤ TTM P/E", "unknown", threshold, observed, notes)

    gap_pct = (fwd / ttm - 1.0) * 100.0
    notes.append(f"Forward is {gap_pct:+.1f}% vs TTM.")
    if fwd <= ttm:
        notes.append("Case 1: earnings expected to grow, valuation improving — the healthy setup.")
        return rule(2, "Forward P/E ≤ TTM P/E", "pass", threshold, observed, notes)
    if gap_pct <= T["pe_forward_tolerance_pct"]:
        notes.append("Case 2: forward ≈ TTM. Earnings expected flat; price already reflects reality. "
                     "Okay for a stable business, but do not expect big upside — scored fail against a "
                     "strict reading of the rule.")
        return rule(2, "Forward P/E ≤ TTM P/E", "fail", threshold, observed, notes)
    hard = gap_pct > T["pe_hard_fail_pct"]
    notes.append("Case 3: forward above TTM — earnings expected to decline or forecasts were cut. "
                 "P/E is expanding, so price is vulnerable to valuation shock.")
    if hard:
        notes.append(f"Gap exceeds the {T['pe_hard_fail_pct']:.0f}% hard-fail band → avoid or reduce.")
    return rule(2, "Forward P/E ≤ TTM P/E", "fail", threshold, observed, notes, hard_fail=hard)


# --------------------------------------------------------------------------
# Rule 3 -- EMA12 above EMA21 (swing trend), buy on the EMA21 pullback
# --------------------------------------------------------------------------
RULE3_NAME = "EMA12 above EMA21 + EMA21 pullback"


def rule_trend(metrics, T):
    ma = metrics.get("moving_averages") or {}
    price = dig(metrics, "price", "close")
    ema12, ema21 = ma.get("ema12"), ma.get("ema21")
    d21 = ma.get("price_vs_ema21_pct")
    ma200, d200 = ma.get("ma200"), ma.get("price_vs_ma200_pct")

    threshold = f"EMA12 > EMA21 and close >= EMA21; ideal entry within {T['pullback_band_pct']:g}% of EMA21"
    observed = (f"price {fmt(price)}; EMA12 {fmt(ema12)}, EMA21 {fmt(ema21)} ({fmt(d21, '%')}); "
                f"MA200 {fmt(ma200)} ({fmt(d200, '%')})")
    notes = []

    if price is None or ema12 is None or ema21 is None:
        notes.append("Price or EMA12/EMA21 unavailable — trend rule cannot be scored.")
        return rule(3, RULE3_NAME, "unknown", threshold, observed, notes)

    if ema12 < ema21:
        notes.append("EMA12 is below EMA21 — swing trend is down. This is the strategy's exit condition, "
                     "so it is a hard fail: no new entry until EMA12 crosses back above EMA21.")
        return rule(3, RULE3_NAME, "fail", threshold, observed, notes, hard_fail=True)

    if ma200 is not None and price < ma200:
        notes.append("Context: price is below MA200 — the short-term trend is up inside a longer downtrend; "
                     "expect overhead supply and size down.")
    elif d200 is not None and d200 > T["ma200_no_add_pct"]:
        notes.append(f"Context: {d200:+.1f}% above MA200 — extended versus the long-term average; "
                     "expect sharp pullbacks, keep the EMA21 stop honest.")

    if price < ema21:
        notes.append("EMA12 > EMA21 but price has closed below EMA21 — the pullback has not been bought yet. "
                     "Wait for a close back above EMA21 rather than catching it.")
        return rule(3, RULE3_NAME, "fail", threshold, observed, notes)

    if d21 is not None and d21 <= T["pullback_band_pct"]:
        notes.append(f"Price is {d21:+.1f}% from EMA21 — at the pullback the checklist asks for.")
    elif d21 is not None:
        notes.append(f"Price is {d21:+.1f}% above EMA21 — trend qualifies; entry is a continuation buy, not a "
                     f"pullback. Backtested as acceptable (rules 4–5 still gate it); a dip toward EMA21 is cheaper.")
    return rule(3, RULE3_NAME, "pass", threshold, observed, notes)


# --------------------------------------------------------------------------
# Rule 4 -- above or reclaiming VWAP
# --------------------------------------------------------------------------
def rule_vwap(metrics, T):
    vwap = metrics.get("vwap") or {}
    value = vwap.get("value")
    close = vwap.get("session_close")
    gap = vwap.get("close_vs_vwap_pct")
    threshold = "Close above VWAP, or reclaiming it (dipped below intraday, closed above)"
    observed = f"VWAP {fmt(value)} vs session close {fmt(close)} ({fmt(gap, '%')})"
    notes = []

    if value is None or close is None:
        notes.append("No intraday VWAP available — rule unknown. Supply VWAP from your chart if you want it scored.")
        return rule(4, "Price above or reclaiming VWAP", "unknown", threshold, observed, notes)

    if vwap.get("session_date"):
        notes.append(f"Session {vwap['session_date']}, {vwap.get('bars_used')} × {vwap.get('interval')} bars, "
                     "regular hours.")

    if close > value:
        if vwap.get("reclaimed_vwap"):
            notes.append("Price traded below VWAP intraday and closed back above it — a reclaim, "
                         "which the vault treats as buyers defending the level.")
        else:
            notes.append("Held above VWAP all session — buyers in control, most money in profit, "
                         "pullbacks tend to get bought.")
        status = "pass"
        if gap is not None and gap > T["vwap_overextended_pct"]:
            notes.append(f"But {gap:+.1f}% above VWAP is overextended (>{T['vwap_overextended_pct']:.0f}%) — "
                         "the vault says avoid buying far above VWAP. Downgraded to fail; wait for a pullback to VWAP.")
            status = "fail"
        slope = vwap.get("slope_pct_recent")
        if slope is not None and slope < 0:
            notes.append(f"VWAP slope {slope:+.2f}% over the recent window — flattening/falling, weaker setup.")
        return rule(4, "Price above or reclaiming VWAP", status, threshold, observed, notes)

    notes.append("Close is below VWAP — sellers won the session, most money is losing, rallies tend to be sold.")
    notes.append("VWAP is a single-session signal, so this is a recoverable fail (wait), not a hard fail: "
                 "the vault's hard fails are trend/valuation breaks, and a reclaim can flip this tomorrow.")
    return rule(4, "Price above or reclaiming VWAP", "fail", threshold, observed, notes)


# --------------------------------------------------------------------------
# Rule 5 -- candle + volume confirmation
# --------------------------------------------------------------------------
def market_meaning(color, vr, turnover, lower_wick, small_body, T):
    """The vault's Volume Ratio + Turnover + Candle interpretation table."""
    if vr is None or turnover is None or color is None:
        return None
    inst = T["volume_ratio_institutional"]
    mod = T["volume_ratio_moderate"]
    quiet = T["turnover_pct_quiet"]
    heavy = T["turnover_pct_institutional"]

    if small_body and vr >= inst and turnover >= heavy:
        return "Absorption — accumulation or distribution. Prepare, don't chase."
    if color == "red" and vr >= inst and turnover >= heavy:
        return "Distribution — institutions selling into liquidity. Do NOT buy."
    if color == "red" and lower_wick and vr < mod and turnover >= 2.0:
        return "Institutions defending — wait for confirmation."
    if color == "green" and vr >= 2.0 and turnover >= 2.0:
        return "Mark-up / breakout — very strong institutional involvement."
    if color == "green" and vr >= inst and turnover >= 1.5:
        return "Institutions buying — strong."
    if color == "green" and vr >= mod and quiet <= turnover:
        return "Normal accumulation — moderate; okay to scale in."
    if vr < mod and turnover < quiet:
        return "Quiet, low interest — retail only. Watch and wait."
    if vr < mod and turnover < heavy:
        return "Institutions active but calm (rotation). Watch, don't rush."
    return "Mixed signals — no clean read."


def rule_candle_volume(metrics, T):
    candle = metrics.get("candle") or {}
    volume = metrics.get("volume") or {}
    color = candle.get("color")
    lower_wick_pct = candle.get("lower_wick_pct_of_range")
    body_pct = candle.get("body_pct_of_range")
    vr = volume.get("volume_ratio")
    turnover = volume.get("turnover_pct")
    vol_delta = volume.get("volume_vs_prev_session_pct")

    threshold = (f"Green candle, volume ratio > {T['volume_ratio_institutional']}, "
                 f"turnover > {T['turnover_pct_institutional']:g}%, price near support/VWAP/MA")
    observed = (f"{color or 'candle n/a'}; volume ratio {fmt(vr)}; turnover {fmt(turnover, '%')}; "
                f"lower wick {fmt(lower_wick_pct, '% of range')}")
    notes = []

    long_wick = lower_wick_pct is not None and lower_wick_pct >= T["long_lower_wick_pct"]
    small_body = body_pct is not None and body_pct <= T["small_body_pct"]

    meaning = market_meaning(color, vr, turnover, long_wick, small_body, T)
    if meaning:
        notes.append(f"Interpretation table: {meaning}")

    if color is None or vr is None:
        notes.append("Candle colour or volume ratio missing — cannot confirm who is in control.")
        return rule(5, "Candle + volume confirmation", "unknown", threshold, observed, notes)

    if vol_delta is not None:
        notes.append(f"Volume {vol_delta:+.0f}% vs the previous session.")
    if long_wick:
        notes.append(f"Long lower wick ({lower_wick_pct:.0f}% of range) — lower prices rejected, buyers defending.")
    if small_body:
        notes.append(f"Small body ({body_pct:.0f}% of range) — indecision, not a decisive candle.")

    # Hard fail: distribution.
    if color == "red" and vr >= T["volume_ratio_institutional"] and (turnover is None or turnover >= T["turnover_pct_institutional"]):
        notes.append("Red candle on institutional volume = distribution. The vault's explicit AVOID signal.")
        return rule(5, "Candle + volume confirmation", "fail", threshold, observed, notes, hard_fail=True)

    if turnover is None:
        notes.append("Turnover % unavailable (needs shares outstanding), so institutional involvement "
                     "cannot be confirmed — unknown rather than pass.")
        return rule(5, "Candle + volume confirmation", "unknown", threshold, observed, notes)

    strong_buy = (color == "green"
                  and vr >= T["volume_ratio_institutional"]
                  and turnover >= T["turnover_pct_institutional"])
    if strong_buy:
        notes.append("Green candle + expanding volume + institutional turnover — buying pressure strengthening "
                     "and buyers in control.")
        return rule(5, "Candle + volume confirmation", "pass", threshold, observed, notes)

    if color == "green" and vr < T["volume_ratio_moderate"]:
        notes.append("Green candle on falling volume — weak bullish: price rising but conviction fading.")
    elif color == "red":
        notes.append("Red candle on shrinking volume — selling pressure weakening, but that is a "
                     "pre-condition, not the entry trigger. Wait for the green confirmation candle.")
    elif color == "doji":
        notes.append("Doji — indecision. No confirmation either way.")
    else:
        notes.append("Green candle but volume/turnover below the institutional thresholds — not confirmed.")
    return rule(5, "Candle + volume confirmation", "fail", threshold, observed, notes)


# --------------------------------------------------------------------------
def score(metrics, business, T):
    rules = [
        rule_business(metrics, business),
        rule_pe(metrics, T),
        rule_trend(metrics, T),
        rule_vwap(metrics, T),
        rule_candle_volume(metrics, T),
    ]
    statuses = [r["status"] for r in rules]
    hard = [r for r in rules if r["hard_fail"]]

    if hard:
        verdict = "avoid"
        reason = "hard fail: " + "; ".join(r["name"] for r in hard)
    elif all(s == "pass" for s in statuses):
        verdict = "enter-candidate"
        reason = "all five rules pass"
    else:
        verdict = "wait"
        fails = [r["name"] for r in rules if r["status"] == "fail"]
        unknowns = [r["name"] for r in rules if r["status"] == "unknown"]
        parts = []
        if fails:
            parts.append("failing: " + ", ".join(fails))
        if unknowns:
            parts.append("unknown: " + ", ".join(unknowns))
        reason = "; ".join(parts)

    ranked = sorted(rules, key=lambda r: (0 if r["hard_fail"] else 1, STATUS_ORDER[r["status"]], r["id"]))
    weakest = None if verdict == "enter-candidate" else {
        "id": ranked[0]["id"], "name": ranked[0]["name"], "status": ranked[0]["status"]
    }

    return {
        "schema": SCHEMA,
        "symbol": metrics.get("symbol"),
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_source": metrics.get("data_source"),
        "data_session_date": dig(metrics, "price", "session_date"),
        "data_generated_at_utc": metrics.get("generated_at_utc"),
        "verdict": verdict,
        "verdict_reason": reason,
        "weakest_rule": weakest,
        "counts": {
            "pass": statuses.count("pass"),
            "fail": statuses.count("fail"),
            "unknown": statuses.count("unknown"),
        },
        "rules": rules,
        "thresholds": T,
        "data_warnings": metrics.get("warnings", []),
        "missing_inputs": sorted(set(metrics.get("missing", []))),
        "not_advice": ("This is a mechanical check of the user's own written rules against supplied data. "
                       "It is not investment advice and predicts nothing."),
    }


ICON = {"pass": "PASS", "fail": "FAIL", "unknown": "UNKNOWN"}


def as_markdown(card, metrics):
    lines = [
        f"# Trade check — {card['symbol']} ({card.get('data_session_date') or 'session n/a'})",
        "",
        f"**Verdict: {card['verdict'].upper()}** — {card['verdict_reason']}  ",
        ("Weakest rule: none — all five pass  " if not card["weakest_rule"] else
         f"Weakest rule: #{card['weakest_rule']['id']} {card['weakest_rule']['name']} "
         f"({card['weakest_rule']['status']})  "),
        f"Score: {card['counts']['pass']} pass / {card['counts']['fail']} fail / "
        f"{card['counts']['unknown']} unknown",
        "",
        "| # | Rule | Status | Threshold | Observed |",
        "|---|------|--------|-----------|----------|",
    ]
    for r in card["rules"]:
        lines.append(
            f"| {r['id']} | {r['name']} | **{ICON[r['status']]}**"
            f"{' (hard)' if r['hard_fail'] else ''} | {r['threshold']} | {r['observed']} |"
        )
    lines.append("")
    lines.append("## Rule notes")
    for r in card["rules"]:
        lines.append("")
        lines.append(f"**{r['id']}. {r['name']} — {r['status']}**")
        for note in r["notes"]:
            lines.append(f"- {note}")

    if card["missing_inputs"]:
        lines += ["", "## Missing inputs", ""]
        lines += [f"- `{m}`" for m in card["missing_inputs"]]
    if card["data_warnings"]:
        lines += ["", "## Data warnings", ""]
        lines += [f"- {w}" for w in card["data_warnings"]]

    lines += [
        "",
        "## Data used",
        "",
        f"- Source: {card.get('data_source')} · pulled {card.get('data_generated_at_utc')}",
        f"- Price close: {fmt(dig(metrics, 'price', 'close'))} "
        f"({dig(metrics, 'price', 'session_date')})",
        f"- EMA12 / EMA21: {fmt(dig(metrics, 'moving_averages', 'ema12'))} / "
        f"{fmt(dig(metrics, 'moving_averages', 'ema21'))} "
        f"({fmt(dig(metrics, 'moving_averages', 'price_vs_ema21_pct'), '%')} vs EMA21)\n"
        f"- MA10 / MA30 / MA50 / MA200: {fmt(dig(metrics, 'moving_averages', 'ma10'))} / "
        f"{fmt(dig(metrics, 'moving_averages', 'ma30'))} / {fmt(dig(metrics, 'moving_averages', 'ma50'))} / "
        f"{fmt(dig(metrics, 'moving_averages', 'ma200'))}",
        f"- VWAP: {fmt(dig(metrics, 'vwap', 'value'))} ({dig(metrics, 'vwap', 'session_date')})",
        f"- Volume ratio / turnover: {fmt(dig(metrics, 'volume', 'volume_ratio'))} / "
        f"{fmt(dig(metrics, 'volume', 'turnover_pct'), '%')}",
        f"- TTM / Forward P/E: {fmt(dig(metrics, 'fundamentals', 'pe_ttm'))} / "
        f"{fmt(dig(metrics, 'fundamentals', 'pe_forward'))}",
        "",
        f"> {card['not_advice']}",
    ]
    return "\n".join(lines)


def as_vault_page(card, metrics):
    date = card.get("data_session_date") or card["evaluated_at_utc"][:10]
    front = [
        "---",
        f"ticker: {card['symbol']}",
        f"session_date: {date}",
        f"verdict: {card['verdict']}",
        f"data_source: {card.get('data_source')}",
        f"data_pulled_at_utc: {card.get('data_generated_at_utc')}",
        f"evaluated_at_utc: {card['evaluated_at_utc']}",
        "tags: [trade-check]",
        "---",
        "",
    ]
    body = as_markdown(card, metrics)
    links = [
        "",
        "## References",
        "",
        "- [[Investment Entry Checklist]]",
        "- [[Price-Earnings Ratio]]",
        "- [[Moving Averages]]",
        "- [[VWAP]]",
        "- [[Candle and Volume Confirmation]]",
    ]
    return "\n".join(front) + body + "\n" + "\n".join(links) + "\n"


# --------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description="Score trade-check metrics against the 5-point checklist.")
    parser.add_argument("metrics", help="path to a trade-check.metrics.v1 JSON file, or - for stdin")
    parser.add_argument("--business", choices=["pass", "fail", "unknown"], default="unknown",
                        help="human verdict on rule 1; defaults to unknown")
    parser.add_argument("--thresholds", type=Path, help="JSON file overriding any default threshold")
    parser.add_argument("--format", choices=["md", "json", "both"], default="md")
    parser.add_argument("--out", help="write the chosen format here instead of stdout")
    parser.add_argument("--page-out", help="also write a vault-ready page body here")
    parser.add_argument("--json-out", help="also write the raw scorecard JSON here")
    args = parser.parse_args(argv)

    raw = sys.stdin.read() if args.metrics == "-" else Path(args.metrics).read_text()
    metrics = json.loads(raw)
    if metrics.get("schema") != "trade-check.metrics.v1":
        print(f"warning: unexpected schema {metrics.get('schema')!r}", file=sys.stderr)

    T = dict(DEFAULT_THRESHOLDS)
    if args.thresholds:
        override = json.loads(args.thresholds.read_text())
        unknown = set(override) - set(T)
        if unknown:
            print(f"warning: ignoring unknown thresholds: {', '.join(sorted(unknown))}", file=sys.stderr)
        T.update({k: v for k, v in override.items() if k in T})

    card = score(metrics, args.business, T)

    md = as_markdown(card, metrics)
    js = json.dumps(card, indent=2)
    out = md if args.format == "md" else js if args.format == "json" else md + "\n\n```json\n" + js + "\n```\n"

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(out)

    if args.page_out:
        Path(args.page_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.page_out).write_text(as_vault_page(card, metrics))
        print(f"wrote {args.page_out}", file=sys.stderr)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(js)
        print(f"wrote {args.json_out}", file=sys.stderr)

    return {"enter-candidate": 0, "wait": 10, "avoid": 20}[card["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())