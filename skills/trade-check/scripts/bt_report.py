#!/usr/bin/env python3
"""Render vibe-trading backtest artifacts as a markdown comparison table.

    python3 bt_report.py ~/.vibe-trading/runs/NVDA-ma200 ~/.vibe-trading/runs/NVDA-ema

One column per run directory (needs artifacts/metrics.csv; trades.csv optional).
`--grid` instead renders a ticker x strategy matrix from run dirs named
<TICKER>-<strategy>[-hN] (as bt_prepare.py creates them); each cell is
"return / Sharpe / trades / avg-hold-days", and 0-trade cells show "no trades".
Stdlib only; never touches the vault.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROWS = [  # (label, column, formatter)
    ("Total return", "total_return", lambda v: f"{v:+.0%}"),
    ("Annual return", "annual_return", lambda v: f"{v:.1%}"),
    ("Max drawdown", "max_drawdown", lambda v: f"{v:.0%}"),
    ("Sharpe", "sharpe", lambda v: f"{v:.2f}"),
    ("Profit factor", "profit_factor", lambda v: f"{v:.2f}"),
    ("Trades", "trade_count", lambda v: f"{v:.0f}"),
    ("Win rate", "win_rate", lambda v: f"{v:.0%}"),
    ("Avg hold (days)", "avg_holding_days", lambda v: f"{v:.0f}"),
    ("Max loss streak", "max_consecutive_loss", lambda v: f"{v:.0f}"),
    ("Time invested", "risk_xray_avg_invested", lambda v: f"{v:.0%}"),
    ("Buy & hold", "benchmark_return", lambda v: f"{v:+.0%}"),
]


def load(run_dir: Path):
    with open(run_dir / "artifacts" / "metrics.csv", newline="") as f:
        m = next(csv.DictReader(f))
    trades = []
    tpath = run_dir / "artifacts" / "trades.csv"
    if tpath.exists():
        with open(tpath, newline="") as f:
            trades = [t for t in csv.DictReader(f) if t.get("side") == "sell"]
    return m, trades


def cell(m, col, fmt):
    try:
        return fmt(float(m[col]))
    except (KeyError, ValueError):
        return "n/a"


def grid(dirs):
    cells, tickers, strategies = {}, [], []
    for d in dirs:
        parts = d.name.split("-")
        ticker, strategy = parts[0], parts[1] if len(parts) > 1 else "?"
        if not (d / "artifacts" / "metrics.csv").exists():
            print(f"skipping {d.name}: no artifacts/metrics.csv (not backtested yet)", file=sys.stderr)
            continue
        m, _ = load(d)
        n = float(m.get("trade_count", 0) or 0)
        cells[ticker, strategy] = ("no trades" if n == 0 else
            f"{cell(m, 'total_return', lambda v: f'{v:+.0%}')} / {cell(m, 'sharpe', lambda v: f'{v:.2f}')} / "
            f"{n:.0f} / {cell(m, 'avg_holding_days', lambda v: f'{v:.0f}d')}")
        cells[ticker, "buy&hold"] = cell(m, "benchmark_return", lambda v: f"{v:+.0%}")
        tickers.append(ticker) if ticker not in tickers else None
        strategies.append(strategy) if strategy not in strategies else None
    cols = strategies + ["buy&hold"]
    print("| ticker | " + " | ".join(cols) + " |")
    print("|---|" + "---|" * len(cols))
    for t in tickers:
        print(f"| {t} | " + " | ".join(cells.get((t, c), "n/a") for c in cols) + " |")
    print("\ncell = total return / Sharpe / trades / avg hold")


def main(argv=None):
    args = list(argv if argv is not None else sys.argv[1:])
    as_grid = "--grid" in args
    dirs = [Path(p).expanduser() for p in args if p != "--grid"]
    if not dirs:
        print(__doc__)
        return 2
    if as_grid:
        grid(dirs)
        return 0
    runs = [(d.name, *load(d)) for d in dirs]
    print("| | " + " | ".join(n for n, _, _ in runs) + " |")
    print("|---|" + "---|" * len(runs))
    for label, col, fmt in ROWS:
        print(f"| {label} | " + " | ".join(cell(m, col, fmt) for _, m, _ in runs) + " |")
    for name, _, trades in runs:
        big = [t for t in trades if abs(float(t.get("return_pct") or 0)) >= 15]
        if big:
            print(f"\n**{name} — trades beyond ±15%:**")
            for t in big:
                print(f"- {t['timestamp'][:10]} sell after {float(t['holding_days']):.0f}d: {float(t['return_pct']):+.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
