"""Base agent interface and common data types."""

from __future__ import annotations

import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AgentResult:
    """Result from a single agent test run."""

    agent: str
    bash_commands: list[str] = field(default_factory=list)
    skill_invocations: list[str] = field(default_factory=list)
    agent_spawns: list[dict] = field(default_factory=list)
    file_reads: list[str] = field(default_factory=list)
    file_writes: list[str] = field(default_factory=list)
    assistant_text: str = ""
    errors: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    exit_code: int = 0
    raw_output: str = ""
    timed_out: bool = False


@dataclass
class VerificationCheck:
    """Result of a single verification command."""

    command: str
    passed: bool
    output: str = ""
    error: str = ""


@dataclass
class VerificationResult:
    """All verification checks for a test."""

    checks: list[VerificationCheck] = field(default_factory=list)


class BaseAgent(ABC):
    """Abstract base for agent adapters (Claude, Codex)."""

    name: str = "base"

    def __init__(self, config: dict):
        self.config = config
        self.agent_config = config["agents"].get(self.name, {})

    @abstractmethod
    def build_command(self, prompt: str, cwd: str) -> list[str]:
        """Build the CLI command to execute."""
        ...

    @abstractmethod
    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        """Parse agent output into structured result."""
        ...

    def run(self, prompt: str, cwd: str, env: Optional[dict] = None, timeout: Optional[int] = None) -> AgentResult:
        """Execute the agent with a prompt and return structured results."""
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        timeout = timeout or self.config["runner"].get("timeout", 180)
        cmd = self.build_command(prompt, cwd)

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                env=run_env,
                timeout=timeout,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            result = self.parse_output(proc.stdout, proc.stderr, proc.returncode)
            result.duration_ms = duration_ms
            result.exit_code = proc.returncode
            result.raw_output = proc.stdout
            return result
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start) * 1000)
            return AgentResult(
                agent=self.name,
                duration_ms=duration_ms,
                timed_out=True,
                errors=[f"Timed out after {timeout}s"],
            )
