"""The ``dku_exec`` tool: run agent-supplied bash in an authed context.

Bash is the deliberate superset surface (unlike Cloudflare's JS isolate): it
hosts ``dku`` verbs, JSON payloads (heredoc / ``@file`` / stdin), and
``python3`` with ``dataiku``/``dataikuapi`` in one tool, and lets the agent do
data-flow in-sandbox so only the distilled result returns to the model.
Hosted mode runs this shell in the selected sandbox; local stdio mode is trusted
single-user execution.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from dku_cli.mcp import policy
from dku_cli.mcp.audit import AuditLog
from dku_cli.mcp.sandbox import SandboxBackend
from dku_cli.mcp.sessions import Session

# Max chars per stream returned to the model — keep big intermediate output
# in the sandbox; the agent should filter/aggregate before returning.
_MAX_OUTPUT = 100_000


@dataclass
class ExecResult:
    """Structured result of a ``dku_exec`` call."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool


def result_to_text(result: ExecResult) -> str:
    """Render an ExecResult as the plain-text tool reply.

    No JSON envelope: stdout/stderr reach the model unescaped, which is both
    cheaper (no JSON escaping of every newline/quote in every command's output)
    and unambiguous (agents pattern-matched the envelope's 'stdout' key and
    tried to unwrap it inside their own shell pipelines).
    """
    header = f"exit {result.exit_code}"
    if result.truncated:
        header += " (output truncated)"
    parts = [header]
    if result.stdout:
        parts.append(result.stdout.rstrip("\n"))
    if result.stderr:
        parts.append("--- stderr ---")
        parts.append(result.stderr.rstrip("\n"))
    return "\n".join(parts)


# Non-secret operational vars the sandbox shell legitimately needs. The
# executor builds its env from THIS allowlist — never the full os.environ — so
# the pod's injected admin credential (DKU_API_TICKET), LLM keys, connection
# secrets, etc. are never exposed to agent-supplied shell. DSS auth is injected
# explicitly per call (the caller's bearer, or the pod owner's key over stdio).
_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "PWD",
        "OLDPWD",
        "TERM",
        "HOSTNAME",
        "LANG",
        "LANGUAGE",
        "TZ",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        # DSS backend location (not secret). The auth KEY is injected separately.
        "DKU_URL",
        # Harness markers (not secret) — kept out of hosted agent shells.
        "CLAUDECODE",
        "CLAUDE_CODE",
        "CODEX_SANDBOX",
        "CURSOR",
        "AI_AGENT",
        "DKU_SERVER_HOST",
        "DKU_BACKEND_HOST",
        "DKU_BASE_PROTOCOL",
        "DKU_BASE_PORT",
    }
)
_ENV_ALLOWLIST_PREFIXES = ("LC_",)


def build_env(
    project: str | None = None,
    dss_auth: dict | None = None,
    mode: str = "hosted",
) -> dict:
    """Build the subprocess env for the agent's shell (model A: per-user identity).

    ``hosted`` (multi-tenant HTTP): start from a non-secret allowlist — NEVER the
    full ``os.environ`` — so the host's injected credential and other tenants'
    secrets stay out of agent-supplied shell.

    ``local`` (single-user stdio): inherit the FULL environment. The agent runs
    as the user on their own machine and legitimately needs their PATH, active
    virtualenv, cloud creds, etc. — it already has all of this through the
    harness's own Bash tool, so scrubbing here only makes ``dku_exec`` weaker
    than plain bash for no security gain.

    In both modes the DSS key is (re)injected explicitly from the per-call auth.
    """
    if mode == "local":
        env = dict(os.environ)
    else:
        env = {
            k: v
            for k, v in os.environ.items()
            if k in _ENV_ALLOWLIST or k.startswith(_ENV_ALLOWLIST_PREFIXES)
        }
    dss_auth = dss_auth or {}
    if dss_auth.get("url"):
        env["DKU_URL"] = dss_auth["url"]
    if dss_auth.get("api_key"):
        env["DKU_API_KEY"] = dss_auth["api_key"]
    if project:
        env["DKU_PROJECT"] = project
    # Keep dku output machine-readable and non-interactive.
    env.setdefault("NO_COLOR", "1")
    env.setdefault("CI", "true")
    return env


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= _MAX_OUTPUT:
        return text, False
    dropped = len(text) - _MAX_OUTPUT
    return text[:_MAX_OUTPUT] + f"\n[...truncated {dropped} chars]", True


def _resource_limits(timeout: int, mode: str = "hosted") -> str:
    """Best-effort ulimits prepended to the script (hosted mode only).

    ``local`` single-user mode adds NO cap — it matches the agent's own shell,
    which has none; an absolute process cap here would also break ``dku_exec`` on
    any machine that already has many processes (a common case on a real laptop).

    ``hosted`` keeps a CPU + file-size backstop and a *generous* process cap. The
    cap is 16384 (raised from 1024) so it never trips on a busy multi-tenant host
    — bubblewrap's PID namespace is the real fork-bomb containment there, this is
    just defense-in-depth. ``-v`` is omitted — it breaks python/node.
    """
    if mode == "local":
        return ""
    cpu = max(1, timeout) + 30
    return (
        f"ulimit -t {cpu} 2>/dev/null; "  # CPU seconds
        "ulimit -u 16384 2>/dev/null; "  # max processes — generous fork-bomb backstop
        "ulimit -f 2097152 2>/dev/null; "  # max file size ~2 GiB (disk-fill guard)
    )


def run_exec(
    commands: str,
    *,
    session: Session,
    backend: SandboxBackend,
    mode: str = "hosted",
    cwd: str | None = None,
    project: str | None = None,
    timeout: int = 180,
    audit: AuditLog | None = None,
    dss_auth: dict | None = None,
) -> ExecResult:
    """Run the script, truncate, audit, and return.

    ``mode`` selects strictness: ``hosted`` (multi-tenant) sanitizes ``--dangerous``,
    scrubs the env to an allowlist, and applies ulimits; ``local`` (single-user
    stdio) does none of that — it's an authenticated shell on the user's machine.

    ``cwd`` overrides the working directory — local mode runs in the user's
    project dir so relative paths to their files (CSV uploads, etc.) just work;
    when omitted it falls back to the session's isolated workdir (hosted).
    """
    sanitized = commands if mode == "local" else policy.sanitize(commands)
    workdir = cwd or str(session.workdir)
    env = build_env(project=project, dss_auth=dss_auth, mode=mode)
    if mode != "local":
        # Hosted HTTP agents should not inherit a host HOME path. Point HOME at
        # the writable session directory so tools that create dotfiles/caches
        # stay inside the per-agent state boundary.
        env["HOME"] = workdir
        env["PWD"] = workdir
        env.setdefault("TMPDIR", "/tmp")
    script = _resource_limits(timeout, mode) + sanitized

    started = time.monotonic()
    raw = backend.run(script, cwd=workdir, env=env, timeout=timeout)
    duration_ms = int((time.monotonic() - started) * 1000)

    stdout, t_out = _truncate(raw.stdout)
    stderr, t_err = _truncate(raw.stderr)
    result = ExecResult(
        exit_code=raw.exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        truncated=t_out or t_err,
    )

    if audit is not None:
        audit.record(
            {
                "ts": time.time(),
                "tool": "dku_exec",
                "session": session.key,
                "project": project,
                "backend": backend.name,
                "trust_mode": mode,
                "auth_mode": (dss_auth or {}).get("mode", "none"),
                "commands": sanitized[:2000],
                "exit_code": raw.exit_code,
                "duration_ms": duration_ms,
            }
        )

    return result
