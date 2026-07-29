#!/bin/sh
# Bootstrap the runtime for the Dataiku MCP server, then hand off to it.
#
# This is what the plugin manifests run. It is a shell script rather than Python
# on purpose: its job is to find a runtime, so it cannot be written in the
# language it is looking for. /bin/sh exists on every macOS and Linux host,
# including minimal containers with no python3 at all.
#
# Three tiers, in descending order of preference:
#
#   1. uv on PATH        — `uv run` resolves run_mcp.py's PEP 723 block itself.
#   2. python3 >= the block's requires-python — hand off to launcher.py, which
#      builds a venv under $CLAUDE_PLUGIN_DATA and pip-installs the same deps.
#   3. npx               — borrow uv from npm without installing anything.
#
# The first tier that works becomes the server process. If none do, we exit
# non-zero telling the user to install uv.
#
# stdout is the MCP JSON-RPC stream; everything logged here goes to stderr.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVER="$HERE/run_mcp.py"
PROVISION="$HERE/launcher.py"
NPX_UV_PACKAGE="@manzt/uv@0.8.13"

# launcher.py's "I could not provision an environment" signal (EX_UNAVAILABLE),
# distinct from any exit status the server itself would produce, so a crashing
# server is never mistaken for a missing runtime and restarted on another tier.
PROVISION_UNAVAILABLE=69

log() {
    printf '[dataiku-headless] %s\n' "$*" >&2
}

# Lowest Python the server accepts, as "<major> <minor>", read from its inline
# metadata so this script never carries a second copy of the version floor.
read_min_python() {
    sed -n \
        's/^#[[:space:]]*requires-python[[:space:]]*=[[:space:]]*">=[[:space:]]*\([0-9]\{1,\}\)\.\([0-9]\{1,\}\)".*/\1 \2/p' \
        "$SERVER" | head -n 1
}

# --- Tier 1: uv ---------------------------------------------------------------
# A uv on PATH can still be broken, so probe it before committing to it.
if command -v uv >/dev/null 2>&1 && uv --version >/dev/null 2>&1; then
    log "starting via uv"
    exec uv run --quiet "$SERVER"
fi

# --- Tier 2: python venv ------------------------------------------------------
min_python=$(read_min_python || true)
min_major=${min_python%% *}
min_minor=${min_python##* }
if [ -z "${min_major:-}" ] || [ -z "${min_minor:-}" ] || [ "$min_major" = "$min_python" ]; then
    min_major=3
    min_minor=10
fi

# Unversioned names first: they are usually the newest interpreter present.
candidates="python$min_major python"
minor=20
while [ "$minor" -ge "$min_minor" ]; do
    candidates="$candidates python$min_major.$minor"
    minor=$((minor - 1))
done

# python3, python and python3.13 are routinely the same binary. Resolve each name
# and skip duplicates, so one broken interpreter is not probed a dozen times.
tried=""
for candidate in $candidates; do
    resolved=$(command -v "$candidate" 2>/dev/null) || continue
    case " $tried " in
        *" $resolved "*) continue ;;
    esac
    tried="$tried $resolved"

    # Let the interpreter compare its own version — no string arithmetic in sh.
    "$resolved" -c \
        "import sys; sys.exit(sys.version_info < ($min_major, $min_minor))" \
        >/dev/null 2>&1 || continue

    status=0
    "$resolved" "$PROVISION" || status=$?
    if [ "$status" -ne "$PROVISION_UNAVAILABLE" ]; then
        # Either the server ran (and this is its exit status) or it failed for a
        # reason another runtime would not fix. Either way, do not retry.
        exit "$status"
    fi
    # This interpreter cannot host the server; try the next, then npx.
done

# --- Tier 3: npx-vendored uv --------------------------------------------------
if command -v npx >/dev/null 2>&1; then
    log "starting via npx $NPX_UV_PACKAGE"
    exec npx -y "$NPX_UV_PACKAGE" run --quiet "$SERVER"
fi

# --- Nothing worked -----------------------------------------------------------
log "could not start: no uv, no usable Python, and no npx on PATH."
log "Install uv — https://docs.astral.sh/uv/getting-started/installation/"
log "  curl -LsSf https://astral.sh/uv/install.sh | sh"
log "Alternatively install Python >= $min_major.$min_minor (with the venv module)"
log "or Node.js, which provides npx."
exit 1
