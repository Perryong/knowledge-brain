# plan.md — Automated Markets Research Loop on claude-obsidian

Goal: a recurring loop that pulls market data for US / China / Singapore plus SPX, BTCUSD, XAUUSD, NVDA, MSFT; runs `/autoresearch` for narrative context; ingests everything into the vault via `wiki-ingest`; produces chart analysis; and auto-commits each cycle.

Status: **plan only, nothing built.** Three blockers were found during pre-flight verification (§1) and one of them needs your decision before Phase 1.

---

## 1. Pre-flight findings (verified, not assumed)

| # | Finding | Impact | Fix |
|---|---|---|---|
| B1 | **This directory is not a git repo.** `hooks/hooks.json` PostToolUse auto-commits `wiki/ .raw/ .vault-meta/`, but opens with `[ -d .git ] \|\| exit 0` — it has been silently no-opping. | "Auto git commit each time" does not work today. | `git init` + first commit. No new code — the hook already does the job. |
| B2 | **No working key-free price API.** Verified by curl: Stooq now serves a JS proof-of-work bot-wall (no CSV). Yahoo `query1/v8/finance/chart` returns `HTTP 429` for every symbol. CoinGecko works (`{"bitcoin":{"usd":64545}}`, HTTP 200) but is crypto-only. | Equities, index, and gold have no source yet. | Decision D1 below. |
| B3 | **matplotlib is not installed** (`ModuleNotFoundError`; Python 3.13.14). | No PNG charts. | Either `pip install matplotlib` or ship numeric chart analysis only (§5). |

### Decision D1 — price data source

| Option | Covers | Cost | Verdict |
|---|---|---|---|
| **Twelve Data** | stocks, indices, forex (XAU/USD), crypto — all five instruments from one API | free tier, 800 req/day, 8/min, needs key | **Recommended.** One source, one key, one code path. |
| Alpha Vantage | same coverage | free, 25 req/day | Too tight once regional indices are added. |
| CoinGecko + yfinance | BTC solid; rest via Yahoo scraping | free, no key | Rejected — yfinance rides the same endpoint that just returned 429. |

Everything below assumes Twelve Data. Swapping providers touches exactly one file (`scripts/fetch-market.py`).

---

## 2. Do I need an MCP server? — No.

Checked against the ladder, rung by rung:

- **Market data MCP** — not needed. A market-data MCP is a process to install, configure, authenticate, and debug in exchange for what `curl` + 30 lines of stdlib `json` already does. Add one only if you later want price lookups inside a conversation where the shell is unavailable.
- **Obsidian MCP** — not needed, and actively discouraged by this repo. v1.7 replaced MCP with the Obsidian CLI transport; `scripts/detect-transport.sh` walks `CLI → mcp-obsidian → mcpvault → filesystem`. Filesystem is the always-available floor and is what you are on now.
- **Git MCP** — not needed. The PostToolUse hook plus plain `git` covers it.

**Net: zero MCP servers.** One API key in the environment.

## 3. Do I need new agent skills? — Almost none.

The repo already ships what this workflow needs:

- `agents/wiki-ingest.md` — parallel batch ingest, one source per agent. This is the fan-out for 5 instruments + 3 regions. **Reuse as-is.**
- `agents/wiki-lint.md` — weekly health scan. **Reuse as-is.**
- `agents/verifier.md` — read-only pre-commit audit. Use it when changing the *scripts*, not on daily data commits.
- `skills/autoresearch` — already does search → fetch → synthesize → file, and already supports boundary-first topic selection.
- `skills/defuddle` — run before ingesting any news URL; cuts 40-60% of tokens on article pages.
- `scripts/wiki-lock.sh` — mandatory once ingest agents run in parallel (§6).

**One new thing only:** `scripts/fetch-market.py` — a deterministic fetcher. It is a script, not an agent, because fetching a known URL for a known symbol list needs no reasoning. Agents reason; scripts fetch.

**Vault mode: stay on `generic`.** `bin/setup-mode.sh` does not migrate existing files, and your 49 pages are already laid out generically. Switching to PARA now splits the vault across two conventions for no gain.

---

## 4. Architecture

```
cron / loop  ──▶  scripts/fetch-market.py        (deterministic, no LLM)
                    │  writes .raw/market-data/YYYY-MM-DD/<symbol>.json
                    ▼
                 scripts/analyze-market.py       (deterministic, stdlib)
                    │  SMA/RSI/ATR/%chg → <symbol>.analysis.json
                    ▼
                 /autoresearch                   (LLM: why did it move)
                    │  news + macro context per region
                    ▼
                 wiki-ingest agents (parallel, lock-guarded)
                    │
                    ▼
                 wiki/sources/market-data/YYYY-MM-DD.md   daily snapshot
                 wiki/entities/<instrument>.md            evergreen, updated
                 wiki/concepts/<theme>.md                 emergent themes
                    │
                    ▼
                 PostToolUse hook → git add + commit      (already exists)
```

Design rule: **numbers come from scripts, narrative comes from the LLM.** Never let the model transcribe a price — that is how a hallucinated number ends up in a note that later sessions treat as fact.

---

## 5. Chart analysis

Two layers. Ship layer 1; layer 2 is optional.

**Layer 1 — numeric (no dependencies).** `analyze-market.py`, stdlib only, per symbol:
- % change 1d / 5d / 1m / YTD
- SMA 20 / 50 / 200 and price-vs-SMA position
- RSI(14), ATR(14) for volatility regime
- 52w high/low and distance from each
- golden/death cross flag on the 50/200

Rendered into the note as a table. This is what actually feeds analysis — an LLM reasons far better over "RSI 71, price 4.2% above SMA20" than over a PNG.

**Layer 2 — visual (optional, needs `pip install matplotlib`).** 200-day close line + SMA overlay → `_attachments/charts/YYYY-MM-DD-<symbol>.png`, embedded with `![[...]]`. Adds a dependency and ~1MB/month of binary blobs to git. Decide after layer 1 is running.

Skipped deliberately: candlestick rendering, TA-Lib, pattern recognition. Add when the numeric layer measurably falls short.

---

## 6. Concurrency

Parallel ingest agents all write `wiki/index.md`, `wiki/log.md`, `wiki/hot.md` — the exact multi-writer hole `wiki-lock.sh` exists to close.

- Every shared-file write wraps in `wiki-lock.sh acquire` / `release`.
- Cap fan-out at 4 concurrent ingest agents. Eight agents contending on three shared files spend more time blocked than working.
- The PostToolUse hook already defers `git add` while locks are held — no extra work.
- `make test-concurrent` is the existing gate for this. Run it once after wiring.

---

## 7. Phases

**Phase 0 — Unblock (30 min)**
1. `git init && git add -A && git commit -m "baseline: vault before markets loop"`
2. Confirm the hook fires: touch a wiki page, check `git log`.
3. Sign up for Twelve Data, export `TWELVEDATA_API_KEY`.
4. Smoke test: one curl per symbol, confirm 200 + parseable JSON for `SPX`, `BTC/USD`, `XAU/USD`, `NVDA`, `MSFT`, and the regional indices. **If any symbol is unavailable on the free tier, resolve here — not in Phase 3.**

**Phase 1 — Fetcher**
- `scripts/fetch-market.py` — symbol list in one dict at the top; writes dated JSON to `.raw/market-data/`; retries once on 429; exits non-zero if any symbol fails.
- Idempotent: same day = same path = overwrite, never duplicate.
- One `assert`-based `demo()` self-check on the parse path.

**Phase 2 — Analyzer**
- `scripts/analyze-market.py` — stdlib indicators from §5 layer 1.
- Self-check with a hand-computed fixture (RSI and SMA are easy to get subtly wrong; a known-answer test is not optional here).

**Phase 3 — Ingest wiring**
- Daily note template in `_templates/market-daily.md`.
- Ingest reads the analysis JSON, writes the snapshot page, updates each `wiki/entities/<instrument>.md`.
- Lock-guarded. Verify with `make test-concurrent`.

**Phase 4 — Autoresearch layer**
- Per region (US / China / SG): `/autoresearch` on drivers of that session's move.
- `defuddle` every URL before ingest.
- Cap depth at 2 and sources at ~6/region, or a daily run turns into a token furnace.
- Findings file to `wiki/concepts/`, linked from the daily snapshot.

**Phase 5 — Schedule**
- Daily, weekdays, ~30 min after US close (21:00 UTC EDT / 22:00 UTC EST). Crypto is 24/7 but a second run buys little.
- Use the `schedule` skill (cron) for the durable job, not a tight `/loop`. A 5-minute loop against a market that prints one daily bar is 287 wasted runs a day.
- Use `/loop` only for ad-hoc intraday sessions when you are actively watching.
- Weekly: `lint the wiki`. Monthly: `fold the log`.

---

## 8. Enable later, not now

- `bash bin/setup-retrieve.sh` — hybrid BM25 + rerank retrieval. Worth it past ~100 pages; this loop hits that in about three weeks. Turn it on then, not now.
- `bin/setup-dragonscale.sh` — you are partly on it already (`address-counter.txt` = 3, one fold page), but `tiling-thresholds.json` reads `calibrated: false` and tiling lint needs ollama. Calibrate before relying on it.

---

## 9. Open questions

1. **D1** — confirm Twelve Data, or name a provider you already have a key for.
2. **China** — ✅ **Hang Seng (`HSI`)**, locked 2026-07-22.
3. **Chart PNGs** — layer 2 yes or no? Costs a dependency and grows the repo.
4. **Retention** — daily snapshots accumulate forever. Prune raw JSON after 90 days, or keep everything?

---

## 10. What this is not

These notes are market *analysis*, not investment advice, and the loop has no idea whether its source article was accurate. Indicator values are computed and trustworthy; narrative synthesis is model output and should be read as such. Worth a standing disclaimer line in the daily template so future-you reading the vault in a year knows which half is which.
