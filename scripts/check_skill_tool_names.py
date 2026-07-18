"""Guard: every tool the skills name must be a real, registered tool.

The skills route the supervisor to MCP tools by name. If a playbook or reference
names a tool that no longer exists — because the surface was pruned but the prose
was not — the model follows a dead route. `check_skill_links.py` catches dead
*file* links; this catches dead *tool* references.

How it works, and why it can't be fooled by a stale doc:

1. The set of real names is read from the **live FastMCP registry**, not a
   hand-maintained list — imported in a subprocess under both transports and
   unioned (streamable-http swaps `create_upload_dataset` for
   `create_upload_dataset_from_rows`, so the union is the full name space).
2. Every backticked, tool-shaped token in the skill markdown is extracted
   (snake_case identifier, optionally written as a call `name(...)`), then each
   must resolve to either a registered tool or an explicit non-tool ``ALLOWLIST``
   entry (parameters, statuses, recipe-family identifiers, config keys, example
   object names). Anything else is a dead tool reference and fails the check.

Precision over recall on the extraction: camelCase fields (`insightId`),
single-word tokens (`prepare`, `timeout`), and tokens carrying `*`/`:`/`=`/`/`
(`list_*`, `object_type:id`, `allow_edit_project=true`, file paths) are not
tool-shaped and are ignored. What *is* extracted must be accounted for — that is
what makes a reintroduced ghost tool fail.

Run standalone or in CI (and via `tests/test_skill_links.py` in the pytest gate):

    uv run python scripts/check_skill_tool_names.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "dataiku-skills"

# Content between single backticks on one line. Triple-backtick fence markers
# never match (the inner run would have to contain a backtick), so fenced code
# openers like ```python are ignored, not mis-parsed.
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
# A token written as a call: `run_scenario(...)` -> keep the callee.
_CALL = re.compile(r"^([a-z][a-z0-9_]+)\s*\(")
# Tool-name shape: lowercase snake_case with at least one underscore (>=2
# segments). Every real tool matches; single words and camelCase do not.
_IDENT = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")

# Minimum plausible registry size; below this the subprocess import is assumed
# broken and we fail closed rather than pass a tree against an empty name set.
_MIN_REGISTRY = 50

# --------------------------------------------------------------------------- #
# Allowlist: backticked snake_case tokens that are NOT MCP tools.
# Every tool-shaped token in the skills must be a registered tool OR listed here.
# Grouped by kind so an addition is a deliberate, reviewable act.
# --------------------------------------------------------------------------- #
ALLOWLIST: frozenset[str] = frozenset(
    {
        # --- Tool parameters and result fields ---
        "agent_type",
        "allow_edit",
        "allow_edit_project",
        "auto_update_schema",
        "confirmation_id",
        "conversation_id",
        "deletion_impacts",
        "error_kind",
        "include_local",
        "job_type",
        "max_bytes",
        "max_items",
        "min_rows",
        "objects_to_delete",
        "project_key",
        "timeout_seconds",
        "wait_for_completion",
        # --- Cobuild turn statuses / signals (multi-segment ones only;
        #     single-word statuses like completed/error/timeout aren't tokens) ---
        "in_progress",
        "needs_confirmation",
        "transport_outcome_unknown",
        "turn_lost",
        # --- DSS recipe-family identifiers (recipe types, not MCP tools) ---
        "clustering_scoring",
        "embed_documents",
        "extract_content",
        "generate_features",
        "nlp_agent_evaluation",
        "nlp_llm_evaluation",
        "nlp_llm_finetuning",
        "nlp_llm_rag_embedding",
        "nlp_llm_summarization",
        "prediction_scoring",
        "prediction_training",
        "spark_scala",
        "spark_sql_query",
        "sql_query",
        "sql_script",
        "standalone_evaluation",
        # --- Migration / domain identifiers ---
        "data_type",
        # --- Illustrative object/column names in prompt examples ---
        "customer_id",
        "customer_ltv",
        "customers_raw",
        "order_count",
        "orders_raw",
        "total_spend",
    }
)


def _tool_names_for_transport(transport: str) -> set[str]:
    """List the registered tool names under one transport, in a subprocess.

    Import-time transport gating in ``dataiku_mcp`` fixes the surface per process,
    so each transport is listed in its own interpreter and the caller unions them.
    Dummy credentials keep the import self-contained; no tool is ever invoked.
    """
    env = {
        **os.environ,
        "DKU_MCP_TRANSPORT": transport,
        "DKU_DSS_URL": os.environ.get("DKU_DSS_URL", "http://skill-tool-check.invalid"),
        "DKU_API_KEY": os.environ.get("DKU_API_KEY", "check-only-unused"),
    }
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import asyncio, dataiku_mcp;"
            "print('\\n'.join(t.name for t in asyncio.run(dataiku_mcp.mcp.list_tools())))",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"failed to list tools under transport={transport!r}:\n{proc.stderr}"
        )
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def registry_tool_names() -> set[str]:
    """The full space of registered tool names, unioned across both transports."""
    names = _tool_names_for_transport("stdio") | _tool_names_for_transport(
        "streamable-http"
    )
    if len(names) < _MIN_REGISTRY:
        raise SystemExit(
            f"live registry returned only {len(names)} tools (< {_MIN_REGISTRY}); "
            "the import is probably broken — refusing to validate against it."
        )
    return names


def tool_shaped_tokens(text: str) -> set[str]:
    """Every backticked, tool-shaped token in a markdown string."""
    found: set[str] = set()
    for span in _INLINE_CODE.findall(text):
        token = span.strip()
        call = _CALL.match(token)
        if call:
            token = call.group(1)
        if _IDENT.fullmatch(token):
            found.add(token)
    return found


def check() -> tuple[list[str], int, int]:
    """Return (errors, tokens_checked, registry_size)."""
    registry = registry_tool_names()
    valid = registry | ALLOWLIST

    md_files = sorted(SKILL_ROOT.rglob("*.md"))
    errors: list[str] = []
    checked = 0
    for path in md_files:
        tokens = tool_shaped_tokens(path.read_text(encoding="utf-8"))
        checked += len(tokens)
        rel = path.relative_to(SKILL_ROOT)
        for token in sorted(tokens):
            if token not in valid:
                errors.append(
                    f"{rel}: `{token}` is not a registered tool. If it is a real "
                    "non-tool token (parameter, status, recipe family, example "
                    "name), add it to ALLOWLIST in "
                    "scripts/check_skill_tool_names.py; otherwise it is a dead tool "
                    "reference — fix it against references/tool-index.md."
                )
    return errors, checked, len(registry)


def main() -> int:
    if not SKILL_ROOT.is_dir():
        print(f"no skill tree under {SKILL_ROOT}", file=sys.stderr)
        return 1
    errors, checked, registry_size = check()
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(
        f"skill tool names OK: {checked} tool-shaped token(s) checked against "
        f"{registry_size} registered tools; all resolve to a real tool or the "
        "explicit non-tool allowlist"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
