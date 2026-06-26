#!/usr/bin/env bash
# Prefer a Playwright-compatible Python (3.10–3.12). System 3.14 often lacks greenlet wheels.
# Playwright is REQUIRED (no HTTP metrics fallback).
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
  return 1
}

if ! PY="$(pick_python)"; then
  echo "ERROR: No Python with Playwright found." >&2
  echo "Install on 3.10–3.12, e.g.:" >&2
  echo "  python3.11 -m pip install playwright && python3.11 -m playwright install chromium" >&2
  exit 2
fi

echo "Using interpreter: $PY ($("$PY" -V 2>&1))"
exec "$PY" "$ROOT/scripts/perf_matrix.py" "$@"
