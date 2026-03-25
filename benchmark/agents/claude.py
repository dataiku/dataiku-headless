"""Claude Code headless agent adapter."""

from __future__ import annotations

import json

from benchmark.agents.base import AgentResult, BaseAgent


class ClaudeAgent(BaseAgent):
    """Adapter for Claude Code in headless mode (claude -p)."""

    name = "claude"

    def build_command(self, prompt: str, cwd: str) -> list[str]:
        model = self.agent_config.get("model", "opus")
        max_turns = self.config["runner"].get("max_turns", 15)
        return [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "stream-json",  # stream-json gives full tool call traces (json only gives final result)
            "--verbose",
            "--dangerously-skip-permissions",
            "--model",
            model,
            "--max-turns",
            str(max_turns),
        ]

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        result = AgentResult(agent=self.name)

        if not stdout.strip():
            result.errors.append("No output from claude")
            return result

        # stream-json outputs JSONL (one event per line)
        # Each event has a "type" field: "assistant", "tool_result", "result", "system", etc.
        events = []
        for line in stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if events:
            return self._parse_jsonl(events, result)

        # Fallback: try single JSON (--output-format json mode)
        try:
            data = json.loads(stdout)
            return self._parse_single_json(data, result)
        except json.JSONDecodeError:
            pass

        # Last resort: treat as plain text
        result.assistant_text = stdout
        result.bash_commands = self._extract_dku_commands_from_text(stdout)
        return result

    def _parse_single_json(self, data: dict, result: AgentResult) -> AgentResult:
        """Parse the single-JSON output format from claude -p."""
        result.assistant_text = data.get("result", "")

        # Token usage
        usage = data.get("usage", {})
        result.input_tokens = usage.get("input_tokens", 0)
        result.output_tokens = usage.get("output_tokens", 0)
        result.duration_ms = data.get("duration_ms", 0)

        # The single JSON format doesn't include tool call details,
        # but we can extract dku commands from the result text
        result.bash_commands = self._extract_dku_commands_from_text(result.assistant_text)

        return result

    def _parse_jsonl(self, events: list[dict], result: AgentResult) -> AgentResult:
        """Parse JSONL conversation events."""
        text_parts = []

        for event in events:
            event_type = event.get("type", "")
            message = event.get("message", {})

            if event_type == "assistant":
                content = message.get("content", [])
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type", "")

                    if block_type == "text":
                        text_parts.append(block.get("text", ""))

                    elif block_type == "tool_use":
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})
                        self._process_tool_call(tool_name, tool_input, result)

            elif event_type == "result":
                # Final result event
                result.input_tokens = event.get("usage", {}).get("input_tokens", 0)
                result.output_tokens = event.get("usage", {}).get("output_tokens", 0)
                result.duration_ms = event.get("duration_ms", 0)
                if "result" in event:
                    text_parts.append(event["result"])

        result.assistant_text = "\n".join(text_parts)
        return result

    def _process_tool_call(self, name: str, input_data: dict, result: AgentResult):
        """Extract information from a tool call."""
        if name == "Bash":
            cmd = input_data.get("command", "")
            if cmd:
                result.bash_commands.append(cmd)
        elif name == "Skill":
            skill = input_data.get("skill", "")
            if skill:
                result.skill_invocations.append(skill)
        elif name == "Agent":
            result.agent_spawns.append({
                "type": input_data.get("subagent_type", ""),
                "prompt": input_data.get("prompt", "")[:200],
                "description": input_data.get("description", ""),
            })
        elif name == "Read":
            path = input_data.get("file_path", "")
            if path:
                result.file_reads.append(path)
        elif name in ("Write", "Edit"):
            path = input_data.get("file_path", "")
            if path:
                result.file_writes.append(path)

    def _extract_dku_commands_from_text(self, text: str) -> list[str]:
        """Fallback: extract dku commands from plain text output."""
        commands = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("dku "):
                commands.append(stripped)
            # Also catch commands in code blocks
            elif stripped.startswith("$ dku "):
                commands.append(stripped[2:])
        return commands
