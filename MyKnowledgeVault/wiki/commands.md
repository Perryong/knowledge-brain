---
address: c-000007
type: reference
title: Claude-Obsidian Command Reference
status: evergreen
created: 2026-08-23
updated: 2026-08-23
tags:
  - reference
  - claude-obsidian
  - commands
---

# Claude-Obsidian Command Reference

How to drive this vault with claude-obsidian v2.1.0. Updated 2026-08-23: trade-check live data + Tiingo fallback, Vibe-Trading MCP integration. Compiled 2026-08-23 from
the skill definitions in the installed product
(`/Users/perry/Documents/Code/claude-obsidian/skills/*/SKILL.md`).

## Starting a session

```bash
cd ~/Documents/MyKnowledgeVault
claude --plugin-dir /Users/perry/Documents/Code/claude-obsidian
```

Invoke any skill as `/claude-obsidian:<name>`, or just use its trigger phrases
in plain language. Start with `/claude-obsidian:wiki` if unsure — it routes to
the right sub-skill.

## Build and use the wiki

| Command | What it does | Say things like |
|---|---|---|
| `/claude-obsidian:wiki` | Initialize/adopt a vault, diagnose readiness, route work to the right sub-skill | "set up wiki", "adopt this vault", "second brain setup" |
| `/claude-obsidian:wiki-ingest` | Turn supplied sources (pasted text, files staged in `inbox/`, approved URLs) into linked pages with provenance and claim tracking | "ingest this file", "process this source", "batch ingest" |
| `/claude-obsidian:save` | Save one selected answer, decision, or insight from the conversation — never an automatic transcript | "save this", "keep this insight", "file this conversation" |
| `/claude-obsidian:wiki-query` | Answer a question read-only from vault evidence | "query the wiki", "based on the wiki", "summarize the vault" |
| `/claude-obsidian:wiki-lint` | Deterministic, read-only health check: dead links, orphans, frontmatter gaps, provenance errors, stale indexes | "vault health check", "find orphans", "audit wiki health" |

**save vs wiki-ingest:** ingest is for source material you supply (files,
URLs); save is for preserving something the assistant said. Ingest tracks
provenance ledgers; save records one reviewed note.

## Extend the workflow

| Command | What it does | Say things like |
|---|---|---|
| `/claude-obsidian:autoresearch` | Bounded research loop (web egress only with explicit consent), cited dossier, then a separately approved canonical merge | "research this topic", "deep dive into", "investigate and file" |
| `/claude-obsidian:canvas` | Create and update Obsidian JSON Canvas boards (text, file, link, group, edge nodes) | "create canvas", "add to canvas", "visual map" |
| `/claude-obsidian:defuddle` | Optional external cleaner: extract article-like HTTPS pages as readable Markdown before ingestion (needs network consent + configured runner) | "defuddle", "clean this URL", "strip page clutter" |
| `/claude-obsidian:wiki-fold` | Extractive rollup of recent `wiki/log.md` entries; dry-run preview by default | "fold the log", "log rollup", "commit the fold" |
| `/claude-obsidian:wiki-mode` | Read or set the filing methodology: Generic (default), LYT, PARA, or Zettelkasten; routes new notes, never migrates old ones | "what is my vault mode", "switch to PARA", "use LYT" |
| `/claude-obsidian:wiki-retrieve` | Vault-local BM25 retrieval index with optional reranking; caches stay under `.vault-meta/` | "semantic search", "find relevant passages", "rebuild the index" |
| `/claude-obsidian:wiki-cli` | Use the official Obsidian CLI for read-only access (search, backlinks, tags) when installed; writes still go through transactions | "which transport", "Obsidian search", "backlinks" |

## Custom skills

| Command | What it does | Say things like |
|---|---|---|
| `/claude-obsidian:trade-check` | Walk one ticker through the [[Investment Entry Checklist]]: fetches live data (Alpha Vantage, Tiingo fallback) or takes your figures, scores the 5 rules, logs a dated scorecard under `wiki/trade-checks/` | "trade check AAPL", "check this ticker", "should I enter" |

**trade-check data setup** — export before the session; never paste keys into
chat or notes (a pasted key is burned — rotate it):

```bash
export ALPHAVANTAGE_API_KEY=...   # fundamentals + prices (25 calls/day free)
export TIINGO_API_KEY=...         # optional fallback: adjusted daily bars, IEX VWAP
```

- If an Alpha Vantage call fails (quota/outage/no key), that input is rebuilt
  from Tiingo automatically; provenance records which provider served what.
- Tiingo has no forward P/E and its free fundamentals cover only a stale
  Dow-30 list, so rule 2 may stay `unknown` — supply the figure yourself.
- Loss-making tickers have no P/E at all; rule 2 is honestly `unknown`
  (judge on revenue growth / cash flow / margins per [[Price-Earnings Ratio]]).
- Rule 1 (business makes sense) is always yours to assert — never auto-passed.
- Offline re-scoring and threshold experiments spend no quota:
  `av_fetch.py <TICKER> --offline`, then `check_rules.py` with `--thresholds`.
- After editing the skill's scripts or thresholds, run its offline regression:
  `python3 <plugin>/skills/trade-check/scripts/selftest.py` (7 scenarios).

Filed verdicts so far: [[NVDA 2026-08-23]] (wait), [[AAOI 2026-08-23]] (wait).

## Vibe-Trading (analysis engine via MCP)

Installed in `~/.venvs/vibe-trading`; registered as user-scope MCP server
`vibe-trading` (90 finance skills, 10 backtest engines, 462 pre-built alphas,
25 data sources). Its tools appear as `mcp__vibe-trading__*` in any new
session — no plugin flag needed.

| Task | Ask for |
|---|---|
| Backtest the checklist | "backtest: buy MA10/MA50 pullback above MA200, exit close below MA30, on NVDA 2y" |
| Second technical opinion | its `technical-basic` (EMA/ADX/BB/RSI/OBV voting), `candlestick`, `volatility` skills |
| Loss-maker fundamentals (the AAOI case) | `valuation-model`, `fundamental-filter` — judge on growth/cash flow/margins |
| Mine your own history | `trade-journal` / `shadow-account` over the `wiki/trade-checks/` pages |

Division of labour and boundaries:

- **Vibe-Trading analyzes; claude-obsidian records.** Its output enters the
  vault only through `trade-check`, `/claude-obsidian:save`, or
  `/claude-obsidian:wiki-ingest` — it has no direct write path to notes.
- Treat its output as untrusted source material (same injection rules as any
  web source). Shell tools are deliberately NOT enabled on the MCP server.
- It reads the same `ALPHAVANTAGE_API_KEY` / `TIINGO_API_KEY` env vars.
- Research toolkit, not audited execution infra: review anything touching a
  live brokerage yourself first. Remove anytime with
  `claude mcp remove vibe-trading` + `rm -rf ~/.venvs/vibe-trading`.

## Reference skills

| Command | What it provides | Say things like |
|---|---|---|
| `/claude-obsidian:obsidian-markdown` | Correct Obsidian Flavored Markdown: properties, wikilinks, embeds, callouts, tags, block references, math, Mermaid | "how do I write a callout", "Obsidian syntax help" |
| `/claude-obsidian:obsidian-bases` | Native `.base` database views: filters, formulas, properties, summaries, table/card/list views | "make a reading list base", "dynamic table" |
| `/claude-obsidian:think` | Structured 10-stage reasoning review for consequential or ambiguous decisions | "think this through", "tradeoff analysis", "postmortem" |

## Portable CLI (outside a Claude session)

Wrapper: `python3 /Users/perry/Documents/Code/claude-obsidian/scripts/claude-obsidian.py`

| Command | Effect |
|---|---|
| `doctor --vault PATH` | Show vault selection and readiness |
| `lint --vault PATH [--as-of YYYY-MM-DD]` | Deterministic health findings |
| `init` / `adopt` / `migrate` | Plan, then apply with `--approved-plan-sha256 HASH --apply` |
| `capture plan` / `capture apply` | Preview, then create immutable copies of `inbox/` sources |
| `transaction inspect` / `apply` / `recover` | Validate, apply, or recover one operation bundle |
| `checkpoint OPERATION_ID --vault PATH` | Explicit Git checkpoint of a completed operation |

Every mutating command previews a JSON plan first; re-run the exact pinned
command with the plan's `--approved-plan-sha256` and `--apply` (or
`--approved-plan-sha256` alone for `transaction apply`).

## Ground rules the skills share

- One logical operation = one inspected, recoverable transaction; no silent
  overwrites.
- Web egress always requires explicit consent; the vault is local-first.
- Sources are captured immutably under `.raw/captured/` before synthesis;
  claims stay linked to evidence in the ledgers.
- Removing the plugin never removes this vault.

See the [[index|Wiki Index]].
