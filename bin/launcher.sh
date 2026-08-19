#!/bin/sh
# LEGACY / INACTIVE: Plugin manifests now invoke ``uv run --quiet
# bin/run_mcp.py`` directly so that native Windows hosts are supported. This
# launcher is retained for possible future fallback use, but no supported
# installation path invokes it. Do not treat it as the active server entry
# point without explicitly restoring manifest support and reviewing its
# platform behavior.
# Bootstrap the runtime for the Dataiku MCP server, then hand off to it.
#
# This legacy fallback is a shell script rather than Python on purpose: its job
# is to find a runtime, so it cannot be written in the language it is looking
# for. /bin/sh exists on every macOS and Linux host, including minimal
# containers with no python3 at all.
#
# Three tiers, in descending order of preference:
#
#   1. uv on PATH        — `uv run` resolves run_mcp.py's PEP 723 block itself.
#   2. python3 >= the block's requires-python — build a venv under
#      $CLAUDE_PLUGIN_DATA and pip-install the same dependencies into it.
#   3. npx or pnpx       — borrow uv from npm without installing anything.
#
# The first tier that works becomes the server process. If none do, we exit
# non-zero telling the user to install uv.
#
# stdout is the MCP JSON-RPC stream; everything logged here goes to stderr.

set -eu

HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SERVER="$HERE/run_mcp.py"
NPM_UV_PACKAGE="@dataiku/uv@0.12.0"
NPM_RUNNERS="npx pnpx"

# CLAUDE_PLUGIN_DATA is the harness-provided directory that survives plugin
# updates — the documented home for exactly this kind of generated venv. Outside
# a plugin install it falls back to a dot-dir beside the checkout.
PLUGIN_ROOT=${CLAUDE_PLUGIN_ROOT:-$(CDPATH='' cd -- "$HERE/.." && pwd)}
DATA_DIR=${CLAUDE_PLUGIN_DATA:-$PLUGIN_ROOT/.deps}
VENV_DIR="$DATA_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_MARKER="$VENV_DIR/.installed"

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

# The pinned requirement specifiers from the same block, whitespace separated.
read_dependencies() {
    sed -n '/^# \/\/\/ script$/,/^# \/\/\/$/p' "$SERVER" |
        sed -n '/dependencies/,/]/p' |
        grep -o '"[^"]*"' | tr -d '"'
}

# Build a venv at $VENV_DIR using $1 and install the pinned dependencies into it.
# Returns non-zero when this interpreter cannot host the server — no venv module,
# no ensurepip, an unwritable data directory — so the caller can try another.
# Both commands send stdout to stderr: nothing may reach the JSON-RPC stream.
provision_venv() {
    if [ ! -x "$VENV_PYTHON" ]; then
        log "uv not found — creating a virtual environment (first run only)"
        mkdir -p "$DATA_DIR" >&2 || return 1
        "$1" -m venv "$VENV_DIR" >&2 || return 1
    fi

    dependencies=$(read_dependencies || true)
    if [ -z "$dependencies" ]; then
        log "no dependencies found in $SERVER"
        return 1
    fi

    if [ ! -f "$VENV_MARKER" ] || [ "$(cat "$VENV_MARKER")" != "$dependencies" ]; then
        log "installing dependencies with pip"
        # Unquoted on purpose: one word per specifier. Pins never contain spaces.
        # shellcheck disable=SC2086
        "$VENV_PYTHON" -m pip install --quiet $dependencies >&2 || return 1
        printf '%s\n' "$dependencies" >"$VENV_MARKER" || return 1
    fi
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

    if provision_venv "$resolved"; then
        log "starting via python venv"
        exec "$VENV_PYTHON" "$SERVER"
    fi
    # This interpreter cannot host the server; try the next, then an npm runner.
done

# --- Tier 3: uv vendored through an npm runner --------------------------------
# A runner on PATH is not enough — it also has to be able to fetch the package,
# so probe with --help. That both proves the pair works and warms the download
# the real invocation reuses. npx needs -y to install without prompting (it
# fails outright when non-interactive); pnpx installs without asking.
for runner in $NPM_RUNNERS; do
    command -v "$runner" >/dev/null 2>&1 || continue
    if [ "$runner" = npx ]; then
        assume_yes="-y"
    else
        assume_yes=""
    fi

    if "$runner" $assume_yes "$NPM_UV_PACKAGE" --help >/dev/null 2>&1; then
        log "starting via $runner $NPM_UV_PACKAGE"
        exec "$runner" $assume_yes "$NPM_UV_PACKAGE" run --quiet "$SERVER"
    fi
    log "$runner cannot run $NPM_UV_PACKAGE"
done

# --- Nothing worked -----------------------------------------------------------
log "could not start: no uv, no usable Python, and no working npx or pnpx."
log "Install uv — https://docs.astral.sh/uv/getting-started/installation/"
log "  curl -LsSf https://astral.sh/uv/install.sh | sh"
log "Alternatively install Python >= $min_major.$min_minor (with the venv module),"
log "or Node.js / pnpm, which provide npx and pnpx."
exit 1
