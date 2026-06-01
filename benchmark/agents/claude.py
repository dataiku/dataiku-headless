"""Claude Code CLI adapter — runs `claude --print` inside the bench-agents container."""

from __future__ import annotations

import json
import os
from pathlib import Path

from benchmark.agents.base import (
    PROJECT_ROOT,
    AgentResult,
    DockerAgent,
    _tagged_print,
    copy_skills,
)


class ClaudeCodeAgent(DockerAgent):
    def prepare(self, cfg_dir: Path, fixture_dir: str):  # noqa: ARG002
        (cfg_dir / "settings.json").write_text(
            json.dumps({"analytics_disabled": True, "product_feedback_disabled": True})
        )
        servers = self._resolve_mcp_servers()
        if servers:
            mcp_servers = {
                name: {"type": "http", "url": entry["url"]}
                for name, entry in servers.items()
            }
            (cfg_dir / "mcp.json").write_text(json.dumps({"mcpServers": mcp_servers}))
        root, names = self._resolve_skills()
        copy_skills(root, names, cfg_dir / "skills")

        env = {"CLAUDE_CONFIG_DIR": "/cfg"}
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        return env, []

    def agent_argv(self, prompt: str, max_turns: int | None = None) -> list[str]:
        model = self.agent_config["model"]
        max_turns = max_turns or self.agent_config["max_turns"]
        _, skills = self._resolve_skills()
        servers = self.agent_config.get("mcp_servers") or {}

        allowed = ["Bash"]
        if skills:
            allowed.append("Skill")
        allowed += [f"mcp__{name}" for name in servers]

        cmd = [
            "claude",
            "--verbose",
            "--output-format",
            "stream-json",
            "--print",
            "--permission-mode",
            "bypassPermissions",
            "--model",
            model,
            "--max-turns",
            str(max_turns),
            "--allowedTools",
            ",".join(allowed),
            "--strict-mcp-config",
        ]
        if servers:
            cmd += ["--mcp-config", "/cfg/mcp.json"]
        if self.agent_config.get("effort"):
            cmd += ["--effort", self.agent_config["effort"]]
        if self.agent_config.get("system_prompt"):
            content = (PROJECT_ROOT / self.agent_config["system_prompt"]).read_text()
            cmd += ["--append-system-prompt", content]
        cmd += ["--", prompt]
        return cmd

    def on_stream_line(self, line: str) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        if event.get("type") != "assistant":
            return
        for block in event.get("message", {}).get("content", []):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if name == "Bash":
                cmd = block.get("input", {}).get("command", "")
                if cmd:
                    _tagged_print(self.name, f"$ {cmd.splitlines()[0]}")
            elif name == "Skill":
                skill = block.get("input", {}).get("skill", "")
                if skill:
                    _tagged_print(self.name, f"skill: {skill}")
            elif name.startswith("mcp__"):
                _tagged_print(self.name, f"mcp: {name}")

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        result = AgentResult(agent=self.name)
        if exit_code != 0 and not stdout.strip():
            result.errors.append(
                stderr.strip()[:500] or f"claude exited with code {exit_code}"
            )
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
            etype = event.get("type")

            if etype == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        name = block.get("name", "")
                        tool_input = block.get("input", {})
                        if name == "Skill" and isinstance(tool_input, dict):
                            skill = tool_input.get("skill", "")
                            if skill:
                                result.skill_calls.append(skill)
                            result.tool_calls.append(
                                {"name": name, "input": tool_input}
                            )
                        elif name == "Bash" and isinstance(tool_input, dict):
                            cmd = tool_input.get("command", "")
                            if cmd:
                                result.bash_commands.append(cmd)
                            result.tool_calls.append(
                                {"name": name, "input": tool_input}
                            )
                        elif name.startswith("mcp__"):
                            result.mcp_calls.append(name)
                            result.tool_calls.append(
                                {"name": name, "type": "mcp", "arguments": tool_input}
                            )
                        else:
                            result.tool_calls.append(
                                {"name": name, "input": tool_input}
                            )

            elif etype == "result":
                result.cost_usd = event.get("total_cost_usd") or 0.0
                result.duration_ms = event.get("duration_ms") or 0
                usage = event.get("usage") or {}
                result.input_tokens = (
                    usage.get("input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                )
                result.output_tokens = usage.get("output_tokens", 0)
                if event.get("is_error"):
                    result.errors.append(event.get("subtype") or "execution error")

        result.assistant_text = "\n".join(text_parts)
        return result

    def estimate_partial_usage(self, result: AgentResult, stdout: str) -> None:
        """Lower-bound usage from per-message `assistant` events: sum output, take
        the largest input (cache re-sent each turn). No partial cost is available, so it stays 0."""
        max_input = 0
        sum_output = 0
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "assistant":
                continue
            usage = event.get("message", {}).get("usage") or {}
            msg_input = (
                usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
            )
            max_input = max(max_input, msg_input)
            sum_output += usage.get("output_tokens", 0)

        result.input_tokens = max_input
        result.output_tokens = sum_output
        result.usage_partial = True
