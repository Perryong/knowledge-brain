#!/usr/bin/env bash
# wiki-sync.sh — commit and push vault changes at the end of a skill session.
#
# The PostToolUse hook in hooks/hooks.json already auto-commits wiki/, .raw/
# and .vault-meta/ after every Write|Edit. What it does NOT do is push, so a
# vault could accumulate dozens of local commits that never reach the remote.
# This script closes that gap and is the single code path for both callers:
#
#   1. Skill-level (wiki, wiki-ingest, autoresearch) — invoked as the final
#      step of a run with a MEANINGFUL message ("wiki-ingest: add Karpathy
#      essay + 3 concept pages") instead of the hook's generic timestamp.
#   2. Hook-level (SessionEnd) — the safety net. Pushes whatever the skills
#      committed but failed to push (model skipped the step, session ended
#      early, push failed transiently on the first try).
#
# Because the hook path runs unattended, EVERY failure mode here is non-fatal:
# the script exits 0 and writes a reason to .vault-meta/hook.log. A network
# blip or an auth prompt must never break a skill run or a session teardown.
#
# ── PUSH IS OPT-IN ───────────────────────────────────────────────────────────
# Committing is local and safe. Pushing is network egress that PUBLISHES the
# vault, and `.raw/` is staged unconditionally — so every ingested source
# document goes with it. On a public remote that makes them world-readable.
#
# This script therefore follows the repo's established egress precedent
# (contextual-prefix.py's `--allow-egress`, tiling-check.py's
# `--allow-remote-ollama`): egress is OFF unless explicitly armed. Push
# requires the sentinel `.vault-meta/auto-push.enabled` to exist. Without it
# the script still commits — it just never sends anything anywhere. Upgrading
# the plugin can therefore never turn an existing user into a publisher.
#
#   bash bin/setup-push.sh            # arm it (states the exposure first)
#   touch .vault-meta/auto-push.enabled   # or arm it by hand
#
# Kill switches, checked BEFORE the enable sentinel (all are empty files in
# .vault-meta/, all gitignored so they never propagate to a clone):
#   auto-commit.disabled → skip everything
#   auto-push.disabled   → commit locally but never push
#
# Design notes:
#
#   Explicit pathspec on BOTH add and commit. The v1.9.0 audit (docs/audits/
#   v1.9.0-pre-public-promotion-audit-2026-05-18.md §"The bug") found that a
#   bare `git commit` sweeps in any unrelated file the user staged manually,
#   burying their intent under an auto-commit message. `git commit -- <paths>`
#   commits ONLY those paths regardless of what else sits in the index.
#
#   Caveat inherent to that fix: `git commit -- <paths>` commits WORKTREE
#   content for those paths, bypassing the index. A wiki page partially staged
#   with `git add -p` is committed in full. Accepted — partial staging of
#   generated wiki pages is not a workflow this vault supports.
#
#   Pathspecs are filtered to directories that exist. `git add -- a/ b/` is
#   all-or-nothing: if ANY pathspec matches nothing it aborts with rc=128 and
#   stages NOTHING. A vault with no `.raw/` (deleted for privacy) would
#   otherwise silently stop committing forever, because `git status` is lenient
#   where `git add` is strict.
#
#   Never operates on an enclosing repository. If the vault is a subdirectory
#   of a larger repo, `git rev-parse --show-toplevel` resolves to the monorepo
#   root and a push there would publish unrelated commits. Refuse instead.
#
#   Git runs non-interactively with a timeout. An expired credential helper on
#   an HTTPS remote makes fetch/push block on a terminal prompt; from a
#   SessionEnd hook that hangs teardown until the hook timeout.
#
#   Push is never forced and never auto-rebases. If the remote has moved
#   ahead, the push is refused and reported. Resolving a divergence is a
#   judgement call that belongs to the user, not to an unattended hook.
#
# Usage:
#   wiki-sync.sh sync ["commit message"]   # stage + commit + push
#   wiki-sync.sh status                    # report only, mutate nothing
#   wiki-sync.sh --dry-run sync ["msg"]    # print the plan, mutate nothing
#
# Exit codes: always 0. Read stdout (and .vault-meta/hook.log) for outcome.

set -uo pipefail

PATHSPEC=(wiki/ .raw/ .vault-meta/)
MUTEX_STALE_SEC=120

# --- Portability shims -------------------------------------------------------
# macOS ships neither GNU `timeout` nor GNU `date -r FILE`. Without these two
# shims the script is silently broken there: `timeout … git push` exits 127
# ("command not found") so EVERY push reports failure, and `date -r "$MUTEX"`
# (BSD `date -r` takes epoch seconds, not a path) errors into a 0-second age so
# a stale mutex is never reaped and wiki-sync wedges permanently.

# Run "$@" under a wall-clock limit if any timeout binary exists; else run bare.
# Bare is the correct fallback: GIT_TERMINAL_PROMPT=0 below already removes the
# hang this guards against, so the limit is defence in depth, not a hard dep.
# WIKI_SYNC_NO_TIMEOUT=1 forces the bare path so tests can exercise the macOS
# branch on a machine that does have coreutils.
if [ "${WIKI_SYNC_NO_TIMEOUT:-0}" = "1" ]; then
  _limit() { shift; "$@"; }
elif command -v timeout >/dev/null 2>&1; then
  _limit() { timeout "$@"; }
elif command -v gtimeout >/dev/null 2>&1; then
  _limit() { gtimeout "$@"; }
else
  _limit() { shift; "$@"; }
fi

# Epoch mtime of "$1"; 0 when it cannot be determined (treated as STALE, so an
# unreadable mutex can never wedge the vault). GNU stat is -c, BSD stat is -f.
_mtime() {
  stat -c %Y "$1" 2>/dev/null \
    || stat -f %m "$1" 2>/dev/null \
    || echo 0
}

# Non-interactive git: never block a session teardown on a credential prompt.
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/bin/true
export SSH_ASKPASS=/bin/true
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -oBatchMode=yes}"

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi

CMD="${1:-sync}"
MSG="${2:-}"

# --- Resolve the vault, and refuse anything that isn't it --------------------
# Anchor on THIS script's location, not the caller's cwd: the hook's guards are
# cwd-relative and could otherwise walk us into an enclosing repository.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
VAULT="$(cd "${SCRIPT_DIR}/.." 2>/dev/null && pwd)"
if [ -z "${VAULT:-}" ] || ! cd "$VAULT" 2>/dev/null; then
  echo "wiki-sync: cannot resolve vault root; nothing to do"
  exit 0
fi

LOG=".vault-meta/hook.log"
log() {
  [ -d .vault-meta ] || return 0
  printf '%s wiki-sync: %s\n' "$(date '+%Y-%m-%dT%H:%M:%SZ')" "$1" >> "$LOG" 2>/dev/null
}
say() {
  echo "wiki-sync: $1"
  log "$1"
}

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "wiki-sync: not a git repository; nothing to do"
  exit 0
fi

# `--show-prefix` is empty only when cwd IS the repo root. Comparing against
# `--show-toplevel` would be fragile on Windows, where git prints `C:/…` and
# `pwd` prints `/c/…`.
PREFIX="$(git rev-parse --show-prefix 2>/dev/null)"
if [ -n "$PREFIX" ]; then
  say "vault sits at '$PREFIX' inside a larger repository; refusing to touch the enclosing repo"
  exit 0
fi

# Sanity: this must look like a vault, not just any repo that happens to be here.
if [ ! -d wiki ] || [ ! -d .vault-meta ]; then
  echo "wiki-sync: no wiki/ + .vault-meta/ here; not a vault, nothing to do"
  exit 0
fi

# --- Guards ------------------------------------------------------------------
if [ -f .vault-meta/auto-commit.disabled ]; then
  say "disabled via .vault-meta/auto-commit.disabled; no commit, no push"
  exit 0
fi

# A held wiki-lock means a page write is mid-flight. Committing now would
# capture a half-written tree. Defer — SessionEnd will retry.
if [ -x scripts/wiki-lock.sh ]; then
  LOCK_LIST="$(bash scripts/wiki-lock.sh list 2>/dev/null)"
  LOCK_RC=$?
  if [ "$LOCK_RC" != "0" ]; then
    say "wiki-lock list failed (rc=$LOCK_RC); deferred — unknown lock state"
    exit 0
  fi
  if [ -n "$LOCK_LIST" ]; then
    say "locks held; deferred to avoid a torn commit"
    exit 0
  fi
fi

# --- Self-mutex --------------------------------------------------------------
# A skill-level sync and the SessionEnd hook can fire together and collide on
# .git/index.lock, where the loser reports a bare "commit failed". Serialise
# instead. mkdir is atomic on POSIX; deliberately NOT wiki-lock, which shells
# out to python3 and would add a dependency this script doesn't otherwise need.
MUTEX=".vault-meta/.wiki-sync.lock"

if ! mkdir "$MUTEX" 2>/dev/null; then
  MUTEX_MTIME="$(_mtime "$MUTEX")"
  MUTEX_AGE=$(( $(date +%s) - ${MUTEX_MTIME:-0} ))
  if [ "${MUTEX_MTIME:-0}" != "0" ] && [ "$MUTEX_AGE" -lt "$MUTEX_STALE_SEC" ]; then
    say "another wiki-sync is running (${MUTEX_AGE}s); skipping this one"
    exit 0
  fi
  rmdir "$MUTEX" 2>/dev/null
  mkdir "$MUTEX" 2>/dev/null || { say "could not take sync mutex; skipping"; exit 0; }
fi
trap 'rmdir "$MUTEX" 2>/dev/null || true' EXIT

UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"

# Only pathspecs that exist on disk: `git add` aborts wholesale on a missing one.
EXISTING=()
for p in "${PATHSPEC[@]}"; do
  [ -d "$p" ] && EXISTING+=("$p")
done

pending_commit() {
  [ ${#EXISTING[@]} -eq 0 ] && return 0
  git status --porcelain -- "${EXISTING[@]}" 2>/dev/null
}
unpushed_count() {
  [ -n "$UPSTREAM" ] || { echo 0; return; }
  git rev-list --count "${UPSTREAM}..HEAD" 2>/dev/null || echo 0
}

# --- status ------------------------------------------------------------------
if [ "$CMD" = "status" ]; then
  echo "vault:     $VAULT"
  echo "upstream:  ${UPSTREAM:-<none>}"
  echo "unpushed:  $(unpushed_count) commit(s)"
  if [ -f .vault-meta/auto-push.enabled ]; then
    echo "push:      ARMED (.vault-meta/auto-push.enabled)"
  else
    echo "push:      not armed — commits stay local (arm: bash bin/setup-push.sh)"
  fi
  echo "tracked paths present: ${EXISTING[*]:-<none>}"
  echo "uncommitted:"
  pending_commit | sed 's/^/  /'
  exit 0
fi

if [ "$CMD" != "sync" ]; then
  echo "wiki-sync: unknown command '$CMD' (expected: sync | status)"
  exit 0
fi

# --- Commit ------------------------------------------------------------------
if [ -z "$MSG" ]; then
  MSG="wiki: session sync $(date '+%Y-%m-%d %H:%M')"
fi

if [ ${#EXISTING[@]} -eq 0 ]; then
  echo "wiki-sync: none of ${PATHSPEC[*]} exist; nothing to commit"
elif [ -n "$(pending_commit)" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    echo "wiki-sync: [dry-run] would commit: $MSG"
    pending_commit | sed 's/^/  /'
  else
    git add -- "${EXISTING[@]}" 2>/dev/null

    # Narrow the commit pathspec to roots that ACTUALLY have staged content.
    # `git commit -- <path>` is stricter than `git add`: it aborts if any
    # argument matches nothing known to git (e.g. an empty, untracked .raw/).
    COMMIT_PATHS=()
    for p in "${EXISTING[@]}"; do
      if [ -n "$(git diff --cached --name-only -- "$p" 2>/dev/null)" ]; then
        COMMIT_PATHS+=("$p")
      fi
    done

    if [ ${#COMMIT_PATHS[@]} -eq 0 ]; then
      say "nothing staged after add; skipping commit"
    elif git commit -q -m "$MSG" -- "${COMMIT_PATHS[@]}" 2>/dev/null; then
      say "committed: $MSG"
    else
      say "commit failed; leaving changes staged for review"
    fi
  fi
else
  echo "wiki-sync: no uncommitted vault changes"
fi

# --- Push --------------------------------------------------------------------
# Runs even when the commit step was a no-op: the usual safety-net case is a
# clean tree carrying commits the PostToolUse hook made but never pushed.
if [ -f .vault-meta/auto-push.disabled ]; then
  say "push skipped via .vault-meta/auto-push.disabled ($(unpushed_count) commit(s) held locally)"
  exit 0
fi

# Opt-in gate. Absent sentinel = commit-only. Never publish by default.
if [ ! -f .vault-meta/auto-push.enabled ]; then
  AHEAD="$(unpushed_count)"
  if [ "$AHEAD" != "0" ]; then
    echo "wiki-sync: push not armed — $AHEAD commit(s) held locally. Arm with: bash bin/setup-push.sh"
  fi
  exit 0
fi

if [ -z "$UPSTREAM" ]; then
  say "no upstream tracking branch; skipping push (set one with: git push -u origin \$(git branch --show-current))"
  exit 0
fi

AHEAD="$(unpushed_count)"
if [ "$AHEAD" = "0" ]; then
  echo "wiki-sync: already in sync with $UPSTREAM"
  exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
  # Checked before the fetch: --dry-run is documented to mutate nothing, and a
  # fetch both hits the network and updates remote-tracking refs.
  echo "wiki-sync: [dry-run] would push $AHEAD commit(s) to $UPSTREAM"
  exit 0
fi

# Refuse to push over a diverged remote. Never force, never auto-rebase.
_limit 30 git fetch --quiet 2>/dev/null
BEHIND="$(git rev-list --count "HEAD..${UPSTREAM}" 2>/dev/null || echo 0)"
if [ "$BEHIND" != "0" ]; then
  say "remote is $BEHIND commit(s) ahead — push refused; reconcile manually (git pull --rebase) then re-run"
  exit 0
fi

# Explicit refspec: a bare `git push` under push.default=matching would push
# every matching branch, not just this one.
BRANCH="$(git branch --show-current 2>/dev/null)"
if _limit 60 git push --quiet origin "HEAD:${BRANCH}" 2>/dev/null; then
  say "pushed $AHEAD commit(s) to $UPSTREAM"
else
  say "push failed ($AHEAD commit(s) still local) — check network/credentials, then re-run: bash scripts/wiki-sync.sh sync"
fi

exit 0
