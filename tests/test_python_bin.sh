#!/usr/bin/env bash
# test_python_bin.sh — unit tests for scripts/python-bin.sh.
#
# Hermetic: builds fake interpreters under mktemp and manipulates PATH. Never
# installs anything. Covers:
#   - resolves a working Python 3 on a normal PATH
#   - SKIPS a `python3` that exists but fails when run (the Microsoft Store
#     alias stub — the exact bug this script exists for)
#   - honours a valid WIKI_PYTHON override
#   - ignores an invalid WIKI_PYTHON and falls back rather than wedging
#   - exec mode runs arguments under the resolved interpreter
#   - fails loudly (rc=1 + guidance) when no Python 3 exists at all
#
# Usage: bash tests/test_python_bin.sh

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PB="$ROOT/scripts/python-bin.sh"

PASS=0
FAIL=0
TMPS=()
cleanup() { for d in "${TMPS[@]:-}"; do [ -n "$d" ] && rm -rf "$d"; done; }
trap cleanup EXIT

ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n     %s\n' "$1" "${2:-}"; }

echo "test_python_bin.sh"

REAL_PY="$(bash "$PB" 2>/dev/null)"
if [ -n "$REAL_PY" ]; then ok "resolves a working interpreter ($REAL_PY)"
else bad "resolves a working interpreter" "got nothing"; fi

# --- the Store stub: on PATH, but exits 49 when run --------------------------
# `command -v python3` succeeds for this; only execution reveals it is broken.
STUB="$(mktemp -d)"; TMPS+=("$STUB")
cat > "$STUB/python3" <<'EOF'
#!/usr/bin/env bash
echo "Python was not found; run without arguments to install from the Microsoft Store" >&2
exit 49
EOF
chmod +x "$STUB/python3"

if PATH="$STUB:$PATH" command -v python3 >/dev/null 2>&1; then
  ok "stub is visible to 'command -v' (precondition)"
else
  bad "stub is visible to 'command -v' (precondition)" "stub not on PATH"
fi

GOT="$(PATH="$STUB:$PATH" bash "$PB" 2>/dev/null)"
if [ -n "$GOT" ] && [ "$GOT" != "python3" ]; then
  ok "skips the broken python3 stub (chose '$GOT')"
else
  bad "skips the broken python3 stub" "resolved to '$GOT'"
fi

OUT="$(PATH="$STUB:$PATH" bash "$PB" -c 'print("alive")' 2>/dev/null)"
if [ "$OUT" = "alive" ]; then ok "exec mode works despite the stub"
else bad "exec mode works despite the stub" "got '$OUT'"; fi

# --- WIKI_PYTHON override ----------------------------------------------------
GOT="$(WIKI_PYTHON="$REAL_PY" bash "$PB" 2>/dev/null)"
if [ "$GOT" = "$REAL_PY" ]; then ok "honours a valid WIKI_PYTHON"
else bad "honours a valid WIKI_PYTHON" "got '$GOT'"; fi

GOT="$(WIKI_PYTHON=/definitely/not/python bash "$PB" 2>/dev/null)"
if [ -n "$GOT" ] && [ "$GOT" != "/definitely/not/python" ]; then
  ok "ignores a broken WIKI_PYTHON and falls back"
else
  bad "ignores a broken WIKI_PYTHON and falls back" "got '$GOT'"
fi

# --- exec mode ---------------------------------------------------------------
OUT="$(bash "$PB" -c 'import sys; print(sys.version_info[0])' 2>/dev/null)"
if [ "$OUT" = "3" ]; then ok "exec mode runs under Python 3"
else bad "exec mode runs under Python 3" "got '$OUT'"; fi

# --- no python at all --------------------------------------------------------
EMPTY="$(mktemp -d)"; TMPS+=("$EMPTY")
# Invoke bash by ABSOLUTE path: with PATH= in an assignment prefix, bash
# searches the NEW PATH for the command name too, so a bare `bash` here would
# fail 127 before python-bin.sh ever ran (and symlinking bash into $EMPTY is
# not reliable on Windows, where ln needs privileges).
BASH_ABS="$(command -v bash)"
ERR="$(PATH="$EMPTY" "$BASH_ABS" "$PB" 2>&1)"; RC=$?
if [ "$RC" = "1" ]; then ok "exits 1 when no Python 3 exists"
else bad "exits 1 when no Python 3 exists" "rc=$RC"; fi
case "$ERR" in
  *"App execution aliases"*) ok "error message names the Windows stub fix" ;;
  *) bad "error message names the Windows stub fix" "got: $ERR" ;;
esac

echo
echo "passed: $PASS   failed: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
