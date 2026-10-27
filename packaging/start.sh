#!/bin/sh
# Starts the LogSanitizer web interface (only reachable from this computer).
exec "$(dirname "$0")/cli.sh" serve "$@"
