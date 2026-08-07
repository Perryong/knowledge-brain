#!/usr/bin/env bash
# python-bin.sh — resolve a WORKING Python 3 interpreter, or exec one.
#
# Why this exists: on Windows, `python3` is usually a Microsoft Store "App
# Execution Alias" stub at
#   %LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe
# The stub is on PATH, so `command -v python3` SUCCEEDS. It only fails when
# actually run, printing "Python was not found; run without arguments to
# install from the Microsoft Store" and exiting 49 — while real Python sits
# at `python` / `py -3`.
#
# Every `command -v python3` guard in this repo therefore passed while every
# `python3 …` call silently failed. That took out `wiki-lock.sh` entirely
# (its path validation shells to python3, so acquire/release/peek returned
# 49 and locking became a no-op) and `wiki-mode.py route` (mode routing fell
# back to nothing). Both failed quietly, which is the worst kind.
#
# So: probe by EXECUTION, never by existence.
#
# Usage:
#   PY="$(bash scripts/python-bin.sh)"      # print the interpreter, e.g. "python"
#   bash scripts/python-bin.sh foo.py --flag   # or exec it directly
#
# Override with WIKI_PYTHON if you want a specific interpreter (a venv, say):
#   WIKI_PYTHON=/path/to/venv/bin/python bash scripts/python-bin.sh foo.py
# It is still verified before use — a broken override falls through to the
# probe rather than wedging the caller.
#
# Exit codes: 0 on success. 1 (with a message on stderr) when no working
# Python 3 exists anywhere, so callers can fail loudly instead of silently.

set -uo pipefail

# Does "$@" run and report itself as Python 3? Note $* is deliberately
# unquoted at the call site so "py -3" splits into command + argument.
_works() {
  "$@" -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1
}

_resolve() {
  # Explicit override first, but verify it — never trust it blindly.
  if [ -n "${WIKI_PYTHON:-}" ]; then
    # shellcheck disable=SC2086
    if _works $WIKI_PYTHON; then
      printf '%s' "$WIKI_PYTHON"
      return 0
    fi
    printf 'python-bin: WIKI_PYTHON=%s is not a working Python 3; ignoring\n' \
      "$WIKI_PYTHON" >&2
  fi

  # `python3` first (correct on Linux/macOS), then `python` (Windows real
  # install, and modern `python` is Python 3), then the Windows py launcher.
  local cand
  for cand in "python3" "python" "py -3"; do
    # shellcheck disable=SC2086
    if _works $cand; then
      printf '%s' "$cand"
      return 0
    fi
  done
  return 1
}

PY="$(_resolve)"
if [ -z "$PY" ]; then
  # printf is a shell builtin; `cat` would be an external dependency on the
  # one code path where the environment is already known to be impoverished.
  printf '%s\n' \
    'python-bin: no working Python 3 found (tried python3, python, py -3).' \
    '' \
    'If you are on Windows and `python3` prints "Python was not found", that is the' \
    'Microsoft Store alias stub shadowing a real install. Either:' \
    '  - install Python 3 from python.org, or' \
    '  - turn the stub off: Settings > Apps > Advanced app settings >' \
    '    App execution aliases > disable "python3.exe"' >&2
  exit 1
fi

# No arguments: report the interpreter. With arguments: run them under it.
if [ "$#" -eq 0 ]; then
  printf '%s\n' "$PY"
  exit 0
fi

# shellcheck disable=SC2086
exec $PY "$@"
