#!/usr/bin/env bash
# Prefer a Playwright-compatible Python (3.10–3.12). System 3.14 often lacks greenlet wheels.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pick_python() {
  for c in python3.11 python3.12 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import playwright' 2>/dev/null; then
        echo "$c"
        return 0
      fi
    fi
  done
  # Fall back even without playwright (HTTP timing subset)
  for c in python3.11 python3.12 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      echo "$c"
      return 0
    fi
  done
  echo "python3"
}

PY="$(pick_python)"
echo "Using interpreter: $PY ($("$PY" -V 2>&1))"
exec "$PY" "$ROOT/scripts/perf_matrix.py" "$@"
