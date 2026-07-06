"""Sandbox backends for the ``dku_exec`` tool.

Agent-supplied hosted shell runs in a sandbox so concurrent agents cannot read
each other's files or the host filesystem. ``bubblewrap`` is the secure
filesystem/process baseline; a plain ``subprocess`` backend is the local-dev
fallback used when ``bwrap`` is unavailable (e.g. macOS, or a cluster that
forbids unprivileged user namespaces). A per-session ephemeral-pod backend is
the future kernel-level tier and is not implemented here.

``probe_bubblewrap`` is the load-bearing check: it confirms not just that the
binary exists but that creating an unprivileged user namespace actually works
in this environment — which is exactly what a hardened K8s cluster may block.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

_PROBE_TIMEOUT = 10

# Read-only runtime paths needed for hosted `dku_exec` shells. Deliberately do
# not bind `/`: HTTP agents should see the session workdir plus runtime/cert/DNS
# files, not the host's home dirs, workspace, service-account mounts, or config.
_RUNTIME_RO_PATHS = (
    "/bin",
    "/sbin",
    "/usr",
    "/lib",
    "/lib64",
    "/opt/dku-mcp",
    "/etc/ssl",
    "/etc/pki",
    "/etc/ca-certificates",
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/nsswitch.conf",
    "/etc/passwd",
    "/etc/group",
    "/etc/protocols",
    "/etc/services",
)


def _decode_partial(value) -> str:
    """Decode partial output captured on a ``TimeoutExpired``.

    ``subprocess.TimeoutExpired.stdout`` / ``.stderr`` carry the bytes captured
    before the kill EVEN WHEN the call used ``text=True`` — so feeding them
    straight into ``json.dumps`` later raises. Always return a str.
    """
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    return value


def _runtime_ro_bind_args() -> list[str]:
    existing = [path for path in _RUNTIME_RO_PATHS if os.path.exists(path)]
    parent_dirs = []
    seen_parents = set()
    for path in existing:
        parent = os.path.dirname(path.rstrip("/"))
        if (
            parent
            and parent != "/"
            and parent not in existing
            and parent not in seen_parents
        ):
            parent_dirs.append(parent)
            seen_parents.add(parent)

    args: list[str] = []
    for path in parent_dirs:
        args.extend(["--dir", path])
    for path in existing:
        args.extend(["--ro-bind", path, path])
    return args


@dataclass
class RunResult:
    """Raw result of running a command in a sandbox backend."""

    stdout: str
    stderr: str
    exit_code: int


def probe_bubblewrap() -> bool:
    """Return True if ``bwrap`` exists and can create a user namespace here."""
    if shutil.which("bwrap") is None:
        return False
    try:
        result = subprocess.run(
            [
                "bwrap",
                *_runtime_ro_bind_args(),
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",  # nosec B108 — bubblewrap creates an isolated tmpfs, not the host /tmp
                "true",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_PROBE_TIMEOUT,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class SandboxBackend:
    """Interface: run a bash script with a working dir, env, and timeout."""

    name = "base"

    def run(self, commands: str, *, cwd: str, env: dict, timeout: int) -> RunResult:
        raise NotImplementedError


class SubprocessBackend(SandboxBackend):
    """No isolation beyond cwd/env — local dev only."""

    name = "subprocess"

    def run(self, commands: str, *, cwd: str, env: dict, timeout: int) -> RunResult:
        try:
            proc = subprocess.run(
                ["bash", "-c", commands],
                cwd=cwd,
                env=env,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
            )
            return RunResult(proc.stdout, proc.stderr, proc.returncode)
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                _decode_partial(exc.stdout),
                _decode_partial(exc.stderr) + f"\n[timed out after {timeout}s]",
                124,
            )


class BubblewrapBackend(SandboxBackend):
    """Run inside a bubblewrap jail.

    The jail exposes read-only runtime/cert/DNS paths and a writable session
    dir. It does not bind the host root filesystem. Network stays on by default
    so ``dku`` can reach DSS; pass ``allow_network=False`` to cut egress.
    """

    name = "bubblewrap"

    def __init__(self, *, allow_network: bool = True) -> None:
        self.allow_network = allow_network

    def _wrap(self, cwd: str) -> list[str]:
        args = [
            "bwrap",
            *_runtime_ro_bind_args(),
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",  # nosec B108 — bubblewrap creates an isolated tmpfs, not the host /tmp
            # Bind the session dir AFTER the tmpfs so it stays writable even
            # when sessions live under /tmp.
            "--bind",
            cwd,
            cwd,
            "--chdir",
            cwd,
            "--die-with-parent",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
        ]
        if not self.allow_network:
            args.append("--unshare-net")
        return args

    def run(self, commands: str, *, cwd: str, env: dict, timeout: int) -> RunResult:
        argv = [*self._wrap(cwd), "bash", "-c", commands]
        try:
            proc = subprocess.run(
                argv,
                env=env,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
            )
            return RunResult(proc.stdout, proc.stderr, proc.returncode)
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                _decode_partial(exc.stdout),
                _decode_partial(exc.stderr) + f"\n[timed out after {timeout}s]",
                124,
            )


def select_backend(
    prefer: str = "auto", *, allow_network: bool = True
) -> SandboxBackend:
    """Pick a backend. ``auto`` uses bubblewrap when available, else subprocess.

    ``prefer="subprocess"`` forces the unsandboxed backend (local dev only).
    ``prefer="bubblewrap"`` still falls back to subprocess if bwrap can't run,
    so callers should check ``backend.name`` and refuse multi-tenant hosting
    when it is not ``"bubblewrap"``.
    """
    if prefer == "subprocess":
        return SubprocessBackend()
    if prefer in ("auto", "bubblewrap") and probe_bubblewrap():
        return BubblewrapBackend(allow_network=allow_network)
    return SubprocessBackend()
