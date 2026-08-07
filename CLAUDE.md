# claude-obsidian — Claude + Obsidian Wiki Vault

This folder is both a Claude Code plugin and an Obsidian vault.

**Plugin name:** `claude-obsidian` (v1.7+ "Compound Vault" — see [docs/compound-vault-guide.md](docs/compound-vault-guide.md); v1.8+ adds methodology modes — see [docs/methodology-modes-guide.md](docs/methodology-modes-guide.md))
**Skills:** `/wiki`, `/wiki-ingest`, `/wiki-query`, `/wiki-lint`, `/wiki-cli` (v1.7), `/wiki-retrieve` (v1.7, opt-in), `/wiki-mode` (v1.8)
**Vault path:** This directory (open in Obsidian directly)

## What This Vault Is For

This vault demonstrates the LLM Wiki pattern — a persistent, compounding knowledge base for Claude + Obsidian. Drop any source, ask any question, and the wiki grows richer with every session.

## Vault Structure

```
.raw/           source documents — immutable, Claude reads but never modifies
wiki/           Claude-generated knowledge base
_templates/     Obsidian Templater templates
_attachments/   images and PDFs referenced by wiki pages
```

## How to Use

Drop a source file into `.raw/`, then tell Claude: "ingest [filename]".

Ask any question. Claude reads the index first, then drills into relevant pages.

Run `/wiki` to scaffold a new vault or check setup status.

Run "lint the wiki" every 10-15 ingests to catch orphans and gaps.

## Cross-Project Access

To reference this wiki from another Claude Code project, add to that project's CLAUDE.md:

```markdown
## Wiki Knowledge Base
Path: /path/to/this/vault

When you need context not already in this project:
1. Read wiki/hot.md first (recent context, ~500 words)
2. If not enough, read wiki/index.md
3. If you need domain specifics, read wiki/<domain>/_index.md
4. Only then read individual wiki pages

Do NOT read the wiki for general coding questions or things already in this project.
```

## Plugin Skills

| Skill | Trigger |
|-------|---------|
| `/wiki` | Setup, scaffold, route to sub-skills |
| `ingest [source]` | Single or batch source ingestion |
| `query: [question]` | Answer from wiki content |
| `lint the wiki` | Health check |
| `/save` | File the current conversation as a structured wiki note |
| `/autoresearch [topic]` | Autonomous research loop: search, fetch, synthesize, file |
| `/canvas` | Visual layer: add images, PDFs, notes to Obsidian canvas |
| `/wiki-cli` (v1.7) | Obsidian CLI transport wrapper; default mutation path on desktop |
| `/wiki-retrieve` (v1.7) | Hybrid contextual + BM25 + cosine-rerank retrieval (opt-in via `bash bin/setup-retrieve.sh`) |
| `/wiki-mode` (v1.8) | Methodology modes (LYT / PARA / Zettelkasten / Generic). Set via `bash bin/setup-mode.sh`; consumed by wiki-ingest / save / autoresearch for routing new pages |
| `/think` (v1.9) | The 10-principle thinking loop (OBSERVE-OBSERVE-LISTEN-THINK-CONNECT-CONNECT-FEEL-ACCEPT-CREATE-GROW) as an invocable workflow. Apply to architectural decisions, audits, post-mortems, ambiguous user requests. Every other skill has a "How to think" appendix mapping this framework to its specific work |
| `/obsidian-markdown` | Obsidian Flavored Markdown reference: wikilinks, embeds, callouts, properties, tags, math, canvas syntax. Consult when creating or editing any wiki page |
| `/obsidian-bases` | Create and edit Obsidian Bases (`.base` files) — the native database layer for dynamic tables, card/list views, filters, formulas over vault notes |
| `/defuddle` | Strip ads, nav, and boilerplate from a web page before ingest, leaving clean markdown (40-60% token saving). Pairs with `wiki-ingest` §URL Ingestion |
| `/wiki-fold` | Roll up the last 2^k entries of `wiki/log.md` into a structurally-idempotent fold page under `wiki/folds/`. Extractive only, dry-run by default (DragonScale) |

## Transport (v1.7+)

`scripts/detect-transport.sh` writes `.vault-meta/transport.json` on first run and refreshes weekly. Skills consult it before mutating the vault. Fallback chain: Obsidian CLI → mcp-obsidian → mcpvault → filesystem (always-available floor). Decision tree: [wiki/references/transport-fallback.md](wiki/references/transport-fallback.md).

## Concurrency (v1.7+)

`scripts/wiki-lock.sh` provides per-file advisory locks for safe multi-writer ingest. Every wiki page write should be guarded by `wiki-lock acquire`/`release`. Stale-after default is 60s; cross-process release allowed by design. The PostToolUse hook defers `git add` while locks are held. Closes the latent multi-writer corruption hole from v1.6.

## Methodology Modes (v1.8+)

Pick an organizational style for the vault via `bash bin/setup-mode.sh`. Four modes available: **generic** (v1.7 default — no opinion), **LYT** (Linking Your Thinking — MOCs + atomic notes), **PARA** (Projects/Areas/Resources/Archives), **Zettelkasten** (timestamped IDs, flat, dense linking). The mode is written to `.vault-meta/mode.json` (gitignored by default; `git add -f` to commit). `wiki-ingest`, `save`, and `autoresearch` consult `python3 scripts/wiki-mode.py route <type> "<name>"` before filing new pages — no special-casing needed in the consumer skills. Full guide: [docs/methodology-modes-guide.md](docs/methodology-modes-guide.md). Closes priority gap 5 from the May 2026 compass artifact.

## Pre-commit verifier (v1.7.1+)

After staging changes for a non-trivial workstream but BEFORE running `git commit`, dispatch the `verifier` agent (`agents/verifier.md`). It reads `git diff --cached`, applies the /best-practices six-cut + agent kernel, and returns findings in four tiers (BLOCKER / HIGH / MEDIUM / LOW) with file:line citations. The agent has read-only tools (Read, Grep, Glob, Bash) — it can inspect but never modify, so its output is purely advisory. This closes the loop the v1.7 audit revealed: code went worker → commit with no separate verifier pass, which is how BLOCKER B1 (data-egress consent gap) slipped through. See `docs/audits/v1.7.0-audit-2026-05-17.md` §10 for the retrospective.

## Commit and Push (v1.9.3+)

`scripts/wiki-sync.sh` is the single code path for getting vault changes to the remote. Two callers:

1. **Skills.** `wiki`, `wiki-ingest` and `autoresearch` each close a run with `bash scripts/wiki-sync.sh sync "<meaningful message>"`, so `git log` reads as named units of work instead of a wall of `wiki: auto-commit <timestamp>`.
2. **`SessionEnd` hook.** Safety net — pushes whatever the skills committed but didn't push.

The script stages `wiki/ .raw/ .vault-meta/`, commits with an explicit pathspec (never sweeps in a manually staged file — closes the v1.9.0 audit finding), and pushes. It defers while any `wiki-lock` is held, holds its own mutex so a skill run and the hook can't collide on `.git/index.lock`, refuses to push over a diverged remote, never force-pushes or auto-rebases, runs git non-interactively under a timeout, and exits 0 on every failure path with the reason on stdout and in `.vault-meta/hook.log`. It refuses to act at all if the vault turns out to be a subdirectory of a larger repository.

**Push is opt-in.** Committing is local and safe; pushing is egress that publishes the vault, and `.raw/` is staged unconditionally — so source documents go with it, world-readable on a public remote. Following the same precedent as `contextual-prefix.py --allow-egress` and `tiling-check.py --allow-remote-ollama`, `wiki-sync` will not push unless `.vault-meta/auto-push.enabled` exists. Without it the vault still commits, just never publishes — so upgrading the plugin can't turn an existing user into a publisher.

```bash
bash bin/setup-push.sh            # consent checkpoint: shows remote, visibility, and what ships
bash bin/setup-push.sh --status   # is it armed?
bash bin/setup-push.sh --disable  # disarm
```

Overrides (all gitignored, so they never propagate to a clone): `.vault-meta/auto-push.disabled` blocks push regardless of the sentinel; `.vault-meta/auto-commit.disabled` blocks both.

Tests: `bash tests/test_wiki_sync.sh` (26 assertions, hermetic — temp vault + local bare remote, no network).

## MCP (Optional)

If you configured the MCP server, Claude can read and write vault notes directly.
See `skills/wiki/references/mcp-setup.md` for setup instructions.

## Release Blog Post

After cutting a new release (git tag + `gh release create`), run:

```
/release-blog
```

This generates a blog post on https://agricidaniel.com/blog/, handles cover image generation, SEO metadata, FAQ schema, internal linking, sitemap/llms.txt updates, Vercel deployment, and Google indexing.
