#!/usr/bin/env bash
# test_wiki_sync.sh — unit tests for scripts/wiki-sync.sh.
#
# Hermetic: every case builds a throwaway vault plus a LOCAL BARE REMOTE under
# mktemp. No network, no external deps beyond bash + git + POSIX utilities.
# Covers:
#   - clean tree is a no-op
#   - push is OPT-IN: nothing is pushed without .vault-meta/auto-push.enabled
#   - armed sentinel → commit reaches the remote
#   - a MISSING .raw/ must not kill the commit (git add is all-or-nothing)
#   - an EMPTY .raw/ must not kill the commit (git commit pathspec is strict)
#   - a manually staged file is NEVER swept into the auto-commit (v1.9.0 audit)
#   - diverged remote → push refused, never forced, never rebased
#   - auto-push.disabled / auto-commit.disabled kill switches
#   - a vault nested inside a larger repo is refused
#   - --dry-run mutates nothing
#
# Usage: bash tests/test_wiki_sync.sh

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYNC_SH="$ROOT/scripts/wiki-sync.sh"

PASS=0
FAIL=0
TMPS=()

cleanup() { for d in "${TMPS[@]:-}"; do [ -n "$d" ] && rm -rf "$d"; done; }
trap cleanup EXIT

ok()   { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %s\n     %s\n' "$1" "${2:-}"; }

assert_contains() {
  case "$2" in *"$3"*) ok "$1" ;; *) bad "$1" "expected to contain: $3
     got: $2" ;; esac
}
assert_not_contains() {
  case "$2" in *"$3"*) bad "$1" "expected NOT to contain: $3
     got: $2" ;; *) ok "$1" ;; esac
}

# Build a vault + bare remote. Echoes the vault path.
mkvault() {
  local base vault
  base="$(mktemp -d)"
  TMPS+=("$base")
  git init -q --bare -b main "$base/remote.git"
  git init -q -b main "$base/vault"
  vault="$base/vault"
  (
    cd "$vault" || exit 1
    git config user.email t@t.t
    git config user.name T
    git config commit.gpgsign false
    mkdir -p wiki .raw .vault-meta scripts
    cp "$SYNC_SH" scripts/wiki-sync.sh
    printf '.vault-meta/hook.log\n.vault-meta/auto-push.enabled\n.vault-meta/*.disabled\n.vault-meta/.wiki-sync.lock/\n' > .gitignore
    printf 'seed\n' > wiki/seed.md
    git add -A >/dev/null 2>&1
    git commit -qm seed
    git remote add origin ../remote.git
    git push -qu origin main
  ) >/dev/null 2>&1
  printf '%s' "$vault"
}

arm()  { : > "$1/.vault-meta/auto-push.enabled"; }
sync() { ( cd "$1" && shift && bash scripts/wiki-sync.sh "$@" 2>&1 ); }
remote_log() { git --git-dir="$1/../remote.git" log --oneline 2>/dev/null; }

echo "test_wiki_sync.sh"

# --- 1. clean tree is a no-op ------------------------------------------------
V="$(mkvault)"; arm "$V"
OUT="$(sync "$V" sync "noop")"
assert_contains "clean tree: no changes reported" "$OUT" "no uncommitted vault changes"
assert_contains "clean tree: already in sync" "$OUT" "already in sync"

# --- 2. push is opt-in -------------------------------------------------------
V="$(mkvault)"   # deliberately NOT armed
printf 'p\n' > "$V/wiki/a.md"
OUT="$(sync "$V" sync "wiki: add a")"
assert_contains "unarmed: still commits" "$OUT" "committed:"
assert_contains "unarmed: refuses to push" "$OUT" "push not armed"
assert_not_contains "unarmed: nothing reached remote" "$(remote_log "$V")" "wiki: add a"

# --- 3. armed → reaches the remote -------------------------------------------
arm "$V"
OUT="$(sync "$V" sync "wiki: add a")"
assert_contains "armed: pushes" "$OUT" "pushed"
assert_contains "armed: remote has the commit" "$(remote_log "$V")" "wiki: add a"

# --- 4. MISSING .raw/ must not kill the commit -------------------------------
V="$(mkvault)"; arm "$V"; rm -rf "$V/.raw"
printf 'p\n' > "$V/wiki/b.md"
OUT="$(sync "$V" sync "wiki: add b")"
assert_contains "missing .raw/: still commits" "$OUT" "committed:"
assert_not_contains "missing .raw/: no silent skip" "$OUT" "nothing staged after add"

# --- 5. EMPTY .raw/ must not kill the commit ---------------------------------
V="$(mkvault)"; arm "$V"
printf 'p\n' > "$V/wiki/c.md"
OUT="$(sync "$V" sync "wiki: add c")"
assert_contains "empty .raw/: still commits" "$OUT" "committed:"

# --- 6. a manually staged file is never swept in (v1.9.0 audit) --------------
V="$(mkvault)"; arm "$V"
printf 'private\n' > "$V/USERFILE.md"
( cd "$V" && git add USERFILE.md ) >/dev/null 2>&1
printf 'p\n' > "$V/wiki/d.md"
sync "$V" sync "wiki: add d" >/dev/null
FILES="$( cd "$V" && git show --name-only --format= HEAD )"
assert_not_contains "audit: USERFILE.md not in the commit" "$FILES" "USERFILE.md"
assert_contains "audit: wiki/d.md is in the commit" "$FILES" "wiki/d.md"
assert_contains "audit: USERFILE.md still staged" "$( cd "$V" && git diff --cached --name-only )" "USERFILE.md"

# --- 7. diverged remote → refuse ---------------------------------------------
V="$(mkvault)"; arm "$V"
BASE="$(dirname "$V")"
git clone -q "$BASE/remote.git" "$BASE/other" 2>/dev/null
(
  cd "$BASE/other" && git config user.email o@o.o && git config user.name O
  mkdir -p wiki && printf 'x\n' > wiki/other.md
  git add -A && git commit -qm "from elsewhere" && git push -q
) >/dev/null 2>&1
printf 'p\n' > "$V/wiki/e.md"
OUT="$(sync "$V" sync "wiki: add e")"
assert_contains "diverged: push refused" "$OUT" "push refused"
assert_not_contains "diverged: nothing force-pushed" "$(remote_log "$V")" "wiki: add e"

# --- 8. kill switches --------------------------------------------------------
V="$(mkvault)"; arm "$V"
: > "$V/.vault-meta/auto-push.disabled"
printf 'p\n' > "$V/wiki/f.md"
OUT="$(sync "$V" sync "wiki: add f")"
assert_contains "auto-push.disabled: commits" "$OUT" "committed:"
assert_contains "auto-push.disabled: skips push" "$OUT" "auto-push.disabled"
rm -f "$V/.vault-meta/auto-push.disabled"

: > "$V/.vault-meta/auto-commit.disabled"
printf 'p\n' > "$V/wiki/g.md"
OUT="$(sync "$V" sync "wiki: add g")"
assert_contains "auto-commit.disabled: does nothing" "$OUT" "auto-commit.disabled"
rm -f "$V/.vault-meta/auto-commit.disabled"

# --- 9. vault nested in a larger repo is refused -----------------------------
OUTER="$(mktemp -d)"; TMPS+=("$OUTER")
git init -q -b main "$OUTER" >/dev/null 2>&1
(
  cd "$OUTER" && git config user.email t@t.t && git config user.name T
  mkdir -p sub/wiki sub/.vault-meta sub/scripts
  cp "$SYNC_SH" sub/scripts/wiki-sync.sh
  printf 'x\n' > sub/wiki/a.md
  git add -A && git commit -qm outer
) >/dev/null 2>&1
OUT="$( cd "$OUTER/sub" && bash scripts/wiki-sync.sh sync "should refuse" 2>&1 )"
assert_contains "nested vault: refuses enclosing repo" "$OUT" "refusing to touch the enclosing repo"

# --- 10. --dry-run mutates nothing -------------------------------------------
V="$(mkvault)"; arm "$V"
printf 'p\n' > "$V/wiki/h.md"
BEFORE="$( cd "$V" && git rev-parse HEAD )"
OUT="$(sync "$V" --dry-run sync "wiki: add h")"
AFTER="$( cd "$V" && git rev-parse HEAD )"
assert_contains "dry-run: announces the commit" "$OUT" "[dry-run] would commit"
if [ "$BEFORE" = "$AFTER" ]; then ok "dry-run: HEAD unchanged"; else bad "dry-run: HEAD unchanged" "HEAD moved"; fi
assert_not_contains "dry-run: nothing pushed" "$(remote_log "$V")" "wiki: add h"

# --- 11. macOS branch: no `timeout` binary available -------------------------
# On stock macOS `timeout` does not exist. Calling it blind exits 127 and makes
# every push report failure. WIKI_SYNC_NO_TIMEOUT=1 forces that same code path.
V="$(mkvault)"; arm "$V"
printf 'p\n' > "$V/wiki/i.md"
OUT="$( cd "$V" && WIKI_SYNC_NO_TIMEOUT=1 bash scripts/wiki-sync.sh sync "wiki: add i" 2>&1 )"
assert_contains "no-timeout branch: still pushes" "$OUT" "pushed"
assert_contains "no-timeout branch: remote has it" "$(remote_log "$V")" "wiki: add i"

# --- 12. stale mutex is reaped, live mutex blocks ----------------------------
V="$(mkvault)"; arm "$V"
printf 'p\n' > "$V/wiki/j.md"
mkdir -p "$V/.vault-meta/.wiki-sync.lock"
OUT="$(sync "$V" sync "wiki: add j")"
assert_contains "live mutex: skips" "$OUT" "another wiki-sync is running"
# Backdate it past MUTEX_STALE_SEC (120s) so it must be reaped.
touch -d '2000-01-01' "$V/.vault-meta/.wiki-sync.lock" 2>/dev/null \
  || touch -t 200001010000 "$V/.vault-meta/.wiki-sync.lock" 2>/dev/null
OUT="$(sync "$V" sync "wiki: add j")"
assert_contains "stale mutex: reaped and proceeds" "$OUT" "committed:"

# --- 13. setup-push GitHub slug parsing (no network) -------------------------
# A slug that keeps its ".git" suffix 404s against the GitHub API, which the
# checkpoint would report as "private" for a repo that is actually PUBLIC —
# the one direction a consent gate must never be wrong in.
SETUP_PUSH="$ROOT/bin/setup-push.sh"
slug_is() {
  local got want
  want="$2"
  got="$(bash "$SETUP_PUSH" --print-slug "$1" 2>/dev/null)"
  if [ "$got" = "$want" ]; then ok "slug: $1"; else bad "slug: $1" "want '$want', got '$got'"; fi
}
slug_is "https://github.com/Perryong/knowledge-brain.git" "Perryong/knowledge-brain"
slug_is "https://github.com/Perryong/knowledge-brain"     "Perryong/knowledge-brain"
slug_is "https://github.com/Perryong/knowledge-brain/"    "Perryong/knowledge-brain"
slug_is "git@github.com:Perryong/knowledge-brain.git"     "Perryong/knowledge-brain"
slug_is "ssh://git@github.com/Perryong/knowledge-brain.git" "Perryong/knowledge-brain"

echo
echo "passed: $PASS   failed: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
