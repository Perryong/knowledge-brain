---
type: meta
title: "Hot Cache"
updated: 2026-07-27
tags:
  - meta
  - hot-cache
status: evergreen
related:
  - "[[index]]"
  - "[[log]]"
  - "[[Research AI Engineer Role 2026]]"
  - "[[AI Engineer Skill Checklist 2026]]"
---

# Recent Context

Navigation: [[index]] | [[log]] | [[overview]]

## Last Updated
2026-07-27 (auto-commit hook verified live)

## Key Recent Facts
- **This vault now runs two workstreams**: (1) an automated **markets loop**, (2) on-demand **autoresearch**.
- **Markets loop**: `bin/run-market-loop.sh` (cron 06:30 SGT Tue–Sat) fetches 6 instruments (SPY, EWH=Hang Seng proxy, NVDA, MSFT, XAUUSD, BTCUSD) via Twelve Data → computes indicators → writes daily snapshot + entity history → commits + pushes to `github.com/Perryong/knowledge-brain`. Scripts: `fetch-market.py`, `analyze-market.py`, `render-market.py`. Key on-disk only (`~/.config/market-loop.env`), never tracked.
- **AI Engineer research (2026-07-27)**: 14 pages filed. Synthesis [[Research AI Engineer Role 2026]] + actionable [[AI Engineer Skill Checklist 2026]] (mid→senior, 6 domains, 3-phase sequencing). Headline: TypeScript/React/IaC/SSDLC/API-first are **High in SG, Medium global** — never averaged.

## Recent Changes
- Total pages 34 → **72**; sources ingested → 4.
- claude-obsidian plugin **reinstalled** (19 skills, hooks active).
- Two bugs found and **fixed** while building: (a) `wiki-lock.sh` + `allocate-address.sh` needed `flock` (absent on macOS) → **fixed in `b9c5391`** (dropped the redundant global lock; per-file noclobber atomicity suffices); `make test` now 9/9 green and the auto-commit hook fires again; (b) `.gitignore ????-??-??.md` was swallowing daily market snapshots.

## Active Threads
- AI Engineer checklist is a 26-week plan the user works through; may want progress tracking later.
- Consider `launchd` instead of cron for wake-resilience.
- macOS `flock` gap affects any multi-writer vault op — unresolved (dependency install was a stop condition).
- Narrative/market layer stays interactive for now (not cloud-automated).
