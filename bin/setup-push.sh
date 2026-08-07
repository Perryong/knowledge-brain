#!/usr/bin/env bash
# setup-push.sh — arm (or disarm) automatic pushing for this vault.
#
# `scripts/wiki-sync.sh` commits freely but will not push unless
# `.vault-meta/auto-push.enabled` exists. This script is the consent
# checkpoint that creates it: it shows you the remote, tells you whether that
# remote is public, and shows what would be published — then asks.
#
# Mirrors the repo's other egress gates (contextual-prefix.py --allow-egress,
# tiling-check.py --allow-remote-ollama): network egress is opt-in, and the
# thing granting consent has to state what it's granting.
#
# Usage:
#   bash bin/setup-push.sh            # interactive arm
#   bash bin/setup-push.sh --status   # report only
#   bash bin/setup-push.sh --disable  # disarm
#   bash bin/setup-push.sh --yes      # arm non-interactively (scripts/CI)

set -uo pipefail

VAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$VAULT" || exit 1

SENTINEL=".vault-meta/auto-push.enabled"
MODE="${1:-}"

say()  { printf '%s\n' "$*"; }
warn() { printf '!! %s\n' "$*" >&2; }

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  warn "not a git repository — nothing to arm"
  exit 1
fi

REMOTE_URL="$(git remote get-url origin 2>/dev/null || echo '')"
BRANCH="$(git branch --show-current 2>/dev/null || echo '?')"

# --- status ------------------------------------------------------------------
if [ "$MODE" = "--status" ]; then
  if [ -f "$SENTINEL" ]; then say "push: ARMED"; else say "push: not armed (commits stay local)"; fi
  say "remote: ${REMOTE_URL:-<none>}"
  say "branch: $BRANCH"
  [ -f .vault-meta/auto-push.disabled ] && say "override: auto-push.disabled is present — push is blocked regardless"
  exit 0
fi

# --- disable -----------------------------------------------------------------
if [ "$MODE" = "--disable" ]; then
  rm -f "$SENTINEL"
  say "Disarmed. wiki-sync will keep committing locally but will not push."
  exit 0
fi

# --- arm ---------------------------------------------------------------------
if [ -z "$REMOTE_URL" ]; then
  warn "no 'origin' remote configured — add one first:"
  warn "  git remote add origin <url> && git push -u origin $BRANCH"
  exit 1
fi

# Best-effort public/private probe for GitHub HTTPS remotes. Unauthenticated
# GitHub API returns 200 for public repos and 404 for private/nonexistent ones.
VISIBILITY="unknown"
case "$REMOTE_URL" in
  *github.com[:/]*)
    SLUG="$(printf '%s' "$REMOTE_URL" | sed -E 's#.*github\.com[:/]+([^/]+/[^/]+?)(\.git)?/?$#\1#')"
    if command -v curl >/dev/null 2>&1 && [ -n "$SLUG" ]; then
      CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 8 \
        -H 'User-Agent: claude-obsidian-setup-push' \
        "https://api.github.com/repos/${SLUG}" 2>/dev/null || echo 000)"
      case "$CODE" in
        200) VISIBILITY="PUBLIC" ;;
        404) VISIBILITY="private (or unreachable anonymously)" ;;
      esac
    fi
    ;;
esac

RAW_COUNT="$(git ls-files .raw/ 2>/dev/null | wc -l | tr -d ' ')"
WIKI_COUNT="$(git ls-files wiki/ 2>/dev/null | wc -l | tr -d ' ')"

say ""
say "Arming automatic push for this vault"
say "───────────────────────────────────────────────────────────"
say "  remote      : $REMOTE_URL"
say "  branch      : $BRANCH"
say "  visibility  : $VISIBILITY"
say ""
say "Once armed, every skill run and every session end will push:"
say "  wiki/        $WIKI_COUNT tracked file(s)"
say "  .raw/        $RAW_COUNT tracked file(s)   <- your SOURCE DOCUMENTS"
say "  .vault-meta/ runtime state"
say ""
if [ "$VISIBILITY" = "PUBLIC" ]; then
  say "  This remote is PUBLIC. Everything above becomes world-readable,"
  say "  including anything you later drop into .raw/. Published content is"
  say "  cached and indexed by third parties — deleting it later does not"
  say "  fully undo that. Do not arm this on a vault holding personal notes,"
  say "  licensed material, or anything embargoed."
  say ""
fi
say "Reversible at any time:  bash bin/setup-push.sh --disable"
say "───────────────────────────────────────────────────────────"

if [ "$MODE" != "--yes" ]; then
  if [ ! -t 0 ]; then
    warn "non-interactive shell and --yes not given; refusing to arm silently"
    exit 1
  fi
  printf 'Arm automatic push to this remote? [y/N] '
  read -r REPLY
  case "$REPLY" in
    y|Y|yes|YES) ;;
    *) say "Not armed. Nothing changed."; exit 0 ;;
  esac
fi

mkdir -p .vault-meta 2>/dev/null
: > "$SENTINEL"
say "Armed. wiki-sync will now push after skill runs and at session end."
say "Disarm with: bash bin/setup-push.sh --disable"
