"""Run an agent CLI inside the bench-agents container (the isolation boundary)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILLS_ROOT = PROJECT_ROOT / "dataiku-devkit/skills"
SCRATCH = PROJECT_ROOT / "benchmark" / ".bench_scratch" / "cfg"

CONTAINER_WORK = "/work"
# Defense in depth only: a login shell re-adds ~/.local/bin, so the real dku strip
# is shadowing LOCAL_BIN with an empty dir (see _docker_cmd), not this PATH.
STRIPPED_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"
# dku is the only thing in ~/.local/bin; shadowing it removes dku for strip profiles.
LOCAL_BIN = "/home/agent/.local/bin"

_print_lock = threading.Lock()


def _tagged_print(agent_name: str, msg: str) -> None:
    with _print_lock:
        print(f"  [{agent_name}] {msg}", flush=True)


@dataclass
class AgentResult:
    agent: str
    bash_commands: list[str] = field(default_factory=list)
    skill_calls: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    mcp_calls: list[str] = field(default_factory=list)
    assistant_text: str = ""
    errors: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    exit_code: int = 0
    timed_out: bool = False
    # Harness raised before scoring; recorded so the run isn't dropped from the denominator.
    errored: bool = False
    cost_usd: float = 0.0
    # Token/cost figures are a lower bound from a killed stream, not a final tally.
    usage_partial: bool = False
    raw_stdout: str = ""
    raw_stderr: str = ""


@dataclass
class OutcomeCheckResult:
    check_name: str
    command: str
    passed: bool
    message: str = ""
    output: str = ""
    exit_code: int = 0


@dataclass
class OutcomeVerification:
    results: list[OutcomeCheckResult] = field(default_factory=list)


class BaseAgent(ABC):
    def __init__(self, config: dict, name: str):
        self.config = config
        self.name = name
        self.agent_config = (config.get("profiles") or {})[name]
        self.verbose: bool = False

    @abstractmethod
    def run(
        self,
        prompt: str,
        cwd: str,
        env: Optional[dict] = None,
        timeout: Optional[int] = None,
        request_context: Optional[dict] = None,
        max_turns: Optional[int] = None,
    ) -> AgentResult: ...


class DockerAgent(BaseAgent):
    """Run an agent CLI inside bench-agents:latest."""

    @abstractmethod
    def prepare(
        self, cfg_dir: Path, fixture_dir: str
    ) -> tuple[dict, list[tuple[str, str]]]:
        """Write CLI config into cfg_dir (/cfg), copy granted skills; return (extra_env, extra_mounts)."""

    @abstractmethod
    def agent_argv(self, prompt: str, max_turns: Optional[int] = None) -> list[str]:
        """The bare CLI argv to exec in the container (working dir /work)."""

    @abstractmethod
    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult: ...

    def estimate_partial_usage(self, result: AgentResult, stdout: str) -> None:
        """Fill token/cost for a killed run from bytes in the stream; an honest lower bound, never fabricated."""

    def on_stream_line(self, line: str) -> None:
        """Called per stdout line when verbose=True."""

    @property
    def has_mcp(self) -> bool:
        return bool(self.agent_config.get("mcp_servers"))

    @property
    def strip_dku(self) -> bool:
        # MCP profiles are MCP-only: the dku CLI is never on PATH for them.
        return bool(self.agent_config.get("strip_dku") or self.has_mcp)

    def _resolve_skills(self) -> tuple[Path, list[str]]:
        """Return (host_skills_root, granted_skill_names)."""
        override = self.agent_config.get("skills_root")
        root = (
            (PROJECT_ROOT / os.path.expandvars(override)).resolve()
            if override
            else SKILLS_ROOT
        )
        if self.agent_config.get("auto_discover_skills"):
            names = (
                [d.name for d in root.iterdir() if d.is_dir()] if root.is_dir() else []
            )
        else:
            names = self.agent_config.get("skills") or []
        return root, names

    def _resolve_mcp_servers(self) -> dict:
        """Map MCP server names to the sidecar URL (no creds; the sidecar holds them)."""
        servers = self.agent_config.get("mcp_servers")
        if not servers:
            return {}
        sidecar = (self.config.get("runner") or {}).get("mcp_sidecar") or {}
        url = sidecar.get("url")
        if not url:
            raise RuntimeError(
                f"profile {self.name!r} declares mcp_servers but no MCP sidecar is "
                "running. The runner must start it before agent runs."
            )
        return {name: {"url": url} for name in servers}

    def run(
        self, prompt, cwd, env=None, timeout=None, request_context=None, max_turns=None
    ):
        timeout = timeout or self.config["runner"].get("timeout", 300)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cfg_dir = Path(tempfile.mkdtemp(prefix=f"{self.name}_", dir=str(SCRATCH)))
        container_name = f"bench_{cfg_dir.name}"
        try:
            extra_env, extra_mounts = self.prepare(cfg_dir, cwd)
            cmd = self._docker_cmd(
                cfg_dir, cwd, extra_env, extra_mounts, prompt, container_name, max_turns
            )

            start = time.monotonic()
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            killed = threading.Event()

            def _kill_on_timeout() -> None:
                remaining = timeout - (time.monotonic() - start)
                if remaining > 0:
                    time.sleep(remaining)
                if proc.poll() is None:
                    # Killing the `docker run` client does NOT stop the container;
                    # it would keep billing API calls. Remove the container itself.
                    subprocess.run(
                        ["docker", "rm", "-f", container_name],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    proc.kill()
                    killed.set()

            threading.Thread(target=_kill_on_timeout, daemon=True).start()

            stderr_lines: list[str] = []
            stderr_thread = threading.Thread(
                target=lambda: stderr_lines.extend(proc.stderr)
            )
            stderr_thread.start()

            stdout_lines: list[str] = []
            for line in proc.stdout:
                stdout_lines.append(line)
                if self.verbose:
                    self.on_stream_line(line.rstrip())
            proc.wait()
            stderr_thread.join()
            duration_ms = int((time.monotonic() - start) * 1000)

            raw_stdout = "".join(stdout_lines)
            raw_stderr = "".join(stderr_lines)
            result = self.parse_output(raw_stdout, raw_stderr, proc.returncode)
            result.agent = self.name
            result.exit_code = proc.returncode
            result.duration_ms = result.duration_ms or duration_ms
            result.raw_stdout = raw_stdout[-1_000_000:]
            result.raw_stderr = raw_stderr[-100_000:]
            if killed.is_set():
                result.timed_out = True
                result.errors.append(f"Timed out after {timeout}s")
                # A killed run emits no final usage event, so recover a partial
                # estimate from the stream rather than reporting 0 tokens.
                if result.input_tokens == 0 and result.output_tokens == 0:
                    self.estimate_partial_usage(result, raw_stdout)
                else:
                    result.usage_partial = True
            return result
        finally:
            # Backstop the timeout reaper: force-remove the container on any exit
            # path so no orphaned agent keeps billing API calls. No-op after --rm.
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            shutil.rmtree(cfg_dir, ignore_errors=True)

    def _docker_cmd(
        self,
        cfg_dir,
        fixture_dir,
        extra_env,
        extra_mounts,
        prompt,
        container_name,
        max_turns=None,
    ):
        runner = self.config["runner"]
        image = runner.get("sandbox_image", "bench-agents:latest")
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--name",
            container_name,
            "--add-host",
            "host.docker.internal:host-gateway",
            "-v",
            f"{cfg_dir}:/cfg",
            "-v",
            f"{fixture_dir}:{CONTAINER_WORK}",
            "-w",
            CONTAINER_WORK,
        ]
        for host_path, container_path in extra_mounts:
            cmd += ["-v", f"{host_path}:{container_path}"]
        # Shadow ~/.local/bin with an empty dir — env PATH alone doesn't survive
        # the agent's login shell.
        if self.strip_dku:
            empty_bin = cfg_dir / "empty_local_bin"
            empty_bin.mkdir(parents=True, exist_ok=True)
            cmd += ["-v", f"{empty_bin}:{LOCAL_BIN}"]
        if self.has_mcp:
            network = (runner.get("mcp_sidecar") or {}).get("network")
            if network:
                cmd += ["--network", network]
        if runner.get("sandbox_cpus"):
            cmd += [f"--cpus={runner['sandbox_cpus']}"]
        if runner.get("sandbox_memory"):
            cmd += [f"--memory={runner['sandbox_memory']}"]

        env: dict[str, str] = {}
        # DSS creds reach the agent only for non-MCP profiles; MCP profiles get them via the sidecar.
        if not self.has_mcp:
            for key in ("DKU_URL", "DKU_API_KEY"):
                val = os.environ.get(key)
                if val:
                    env[key] = _to_container_url(val) if key == "DKU_URL" else val
            env["DKU_DANGEROUS"] = "1"
        if self.strip_dku:
            env["PATH"] = STRIPPED_PATH
        env.update(extra_env)
        for key, val in env.items():
            cmd += ["-e", f"{key}={val}"]

        cmd += [image, *self.agent_argv(prompt, max_turns)]
        return cmd


def _to_container_url(url: str) -> str:
    return (
        url.replace("127.0.0.1", "host.docker.internal")
        .replace("0.0.0.0", "host.docker.internal")
        .replace("localhost", "host.docker.internal")
    )


def copy_skills(src_root: Path, names: list[str], dest_dir: Path) -> list[str]:
    """Copy granted skill dirs into dest_dir. Returns the names actually copied."""
    copied: list[str] = []
    if not names:
        return copied
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        src = src_root / name
        if src.is_dir():
            shutil.copytree(src, dest_dir / name)
            copied.append(name)
    return copied
