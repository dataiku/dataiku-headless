"""Codex CLI adapter — runs `codex exec` inside the bench-agents container."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from benchmark.agents.base import (
    CONTAINER_WORK,
    PROJECT_ROOT,
    AgentResult,
    DockerAgent,
    _tagged_print,
    copy_skills,
)

# Per-million-token pricing: (input, cached_input, output)
_MODEL_PRICING: dict[str, tuple[float, float, float]] = {
    "gpt-5.5": (5.0, 0.5, 30.0),
    "gpt-5.4": (2.5, 0.25, 15.0),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
}

# codex discovers skills under $HOME/.agents/skills; HOME is /home/agent in the image.
_CODEX_SKILLS_TARGET = "/home/agent/.agents/skills"


class CodexAgent(DockerAgent):
    def prepare(self, cfg_dir: Path, fixture_dir: str):
        self._write_auth(cfg_dir)
        self._write_config(cfg_dir)
        self._write_agents_md(fixture_dir)

        mounts: list[tuple[str, str]] = []
        root, names = self._resolve_skills()
        copied = copy_skills(root, names, cfg_dir / "skills")
        if copied:
            mounts.append((str(cfg_dir / "skills"), _CODEX_SKILLS_TARGET))

        env = {"CODEX_HOME": "/cfg"}
        return env, mounts

    def _write_auth(self, cfg_dir: Path) -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            (cfg_dir / "auth.json").write_text(
                json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": api_key})
            )

    def _write_config(self, cfg_dir: Path) -> None:
        lines: list[str] = []
        for name, entry in self._resolve_mcp_servers().items():
            lines.append(f"[mcp_servers.{name}]")
            lines.append(f'url = "{entry["url"]}"')
            lines.append("")
        (cfg_dir / "config.toml").write_text("\n".join(lines))

    def _write_agents_md(self, fixture_dir: str) -> None:
        system_prompt = self.agent_config.get("system_prompt")
        if not system_prompt:
            return
        content = (PROJECT_ROOT / system_prompt).read_text()
        (Path(fixture_dir) / "AGENTS.md").write_text(content)

    def agent_argv(self, prompt: str, max_turns: int | None = None) -> list[str]:
        model = self.agent_config["model"]
        effort = self.agent_config.get("effort", "medium")
        max_turns = max_turns or self.agent_config["max_turns"]
        return [
            "codex",
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--enable",
            "unified_exec",
            "-m",
            model,
            "-c",
            f'model_reasoning_effort="{effort}"',
            "-c",
            f"max_agent_turns={max_turns}",
            "-C",
            CONTAINER_WORK,
            "--sandbox",
            "danger-full-access",
            "--",
            prompt,
        ]

    def on_stream_line(self, line: str) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        if event.get("type") != "item.completed":
            return
        item = event.get("item", {})
        if item.get("type") == "command_execution":
            cmd = self._unwrap(item.get("command", ""))
            if cmd:
                _tagged_print(self.name, f"$ {cmd.splitlines()[0]}")
        elif item.get("type") == "mcp_tool_call":
            _tagged_print(self.name, f"mcp: {self._mcp_label(item)}")

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:  # noqa: ARG002
        result = AgentResult(agent=self.name)
        if not stdout.strip():
            result.errors.append(stderr.strip()[:500] or "no output from codex")
            return result

        text_parts: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = event.get("type", "")
            item = event.get("item", {})
            itype = item.get("type", "")

            if etype == "item.completed" and itype == "command_execution":
                cmd = self._unwrap(item.get("command", ""))
                result.bash_commands.append(cmd)
                result.tool_calls.append({"name": "Bash", "input": {"command": cmd}})
            elif etype == "item.completed" and itype == "mcp_tool_call":
                label = self._mcp_label(item)
                result.mcp_calls.append(label)
                call = {
                    "name": label,
                    "type": "mcp",
                    "arguments": item.get("arguments"),
                }
                err = self._mcp_error(item)
                if err:
                    call["error"] = err
                    result.errors.append(f"mcp {label}: {err}")
                result.tool_calls.append(call)
            elif etype == "item.completed" and itype == "agent_message":
                if item.get("text"):
                    text_parts.append(item["text"])
            elif etype == "turn.completed":
                usage = event.get("usage", {})
                result.input_tokens += usage.get("input_tokens", 0)
                result.output_tokens += usage.get("output_tokens", 0)
                result.cost_usd += self._estimate_cost(
                    usage.get("input_tokens", 0),
                    usage.get("cached_input_tokens", 0),
                    usage.get("output_tokens", 0),
                )
            elif etype == "turn.failed":
                result.errors.append(
                    (event.get("error") or {}).get("message") or "turn failed"
                )
            elif etype == "error":
                result.errors.append(event.get("message") or "unknown error")

        result.assistant_text = "\n".join(text_parts)
        result.skill_calls = self._infer_skill_calls(result.bash_commands)
        return result

    def estimate_partial_usage(self, result: AgentResult, stdout: str) -> None:
        """Lower-bound usage for a killed run at ~4 chars/token: tool commands +
        outputs + MCP payloads as input, agent/reasoning text as output."""
        in_chars = 0
        out_chars = 0
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "item.completed":
                continue
            item = event.get("item", {})
            itype = item.get("type", "")
            if itype == "command_execution":
                in_chars += len(item.get("command", "")) + len(
                    item.get("aggregated_output", "")
                )
            elif itype == "mcp_tool_call":
                in_chars += len(json.dumps(item.get("arguments") or {})) + len(
                    json.dumps(item.get("result") or {})
                )
            elif itype == "web_search":
                in_chars += len(item.get("query", ""))
            elif itype in ("agent_message", "reasoning"):
                out_chars += len(item.get("text", ""))

        result.input_tokens = in_chars // 4
        result.output_tokens = out_chars // 4
        result.cost_usd = self._estimate_cost(
            result.input_tokens, 0, result.output_tokens
        )
        result.usage_partial = True

    @staticmethod
    def _infer_skill_calls(bash_commands: list[str]) -> list[str]:
        """Distinct skills consulted, inferred from reads of `skills/<name>/...`, first-seen order."""
        seen: list[str] = []
        for cmd in bash_commands:
            for name in re.findall(r"/skills/([^/\s\"']+)/", cmd):
                if name not in seen:
                    seen.append(name)
        return seen

    @staticmethod
    def _mcp_label(item: dict) -> str:
        server = item.get("server") or item.get("server_name") or ""
        tool = item.get("tool") or item.get("tool_name") or item.get("name") or ""
        return f"{server}.{tool}".strip(".")

    @staticmethod
    def _mcp_error(item: dict) -> str | None:
        """Surface a failed MCP call (top-level `error` or `isError` result), else None."""
        if item.get("error"):
            return str(item["error"])[:300]
        res = item.get("result")
        if isinstance(res, dict) and res.get("isError"):
            content = res.get("content") or []
            texts = [c.get("text", "") for c in content if isinstance(c, dict)]
            return (" ".join(texts) or "isError")[:300]
        return None

    @staticmethod
    def _unwrap(cmd: str) -> str:
        for prefix in ("/bin/zsh -lc '", "/bin/bash -lc '", "/bin/sh -c '"):
            if cmd.startswith(prefix) and cmd.endswith("'"):
                return cmd[len(prefix) : -1]
        return cmd

    def _estimate_cost(self, input_tokens, cached_tokens, output_tokens) -> float:
        price_in, price_cached, price_out = _MODEL_PRICING.get(
            self.agent_config["model"], (2.0, 1.0, 8.0)
        )
        regular_input = max(0, input_tokens - cached_tokens)
        return (
            regular_input * price_in
            + cached_tokens * price_cached
            + output_tokens * price_out
        ) / 1_000_000
