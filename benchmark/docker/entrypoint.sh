#!/usr/bin/env bash
# The host runner passes the full agent argv (e.g. `codex exec ...`). Just exec.
set -euo pipefail
exec "$@"
