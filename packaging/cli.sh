#!/bin/sh
# LogSanitizer command line (Linux). Needs Python 3.10+.
APP="$(cd "$(dirname "$0")" && pwd)"
PY=""
for candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "Python 3.10 oder neuer wurde nicht gefunden." >&2
    exit 1
fi
PYTHONPATH="$APP/backend/src" exec "$PY" -m logsanitizer --workspace "$APP/workspace" "$@"
