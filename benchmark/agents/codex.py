"""Codex CLI headless agent adapter."""

from __future__ import annotations

import json

from benchmark.agents.base import AgentResult, BaseAgent


class CodexAgent(BaseAgent):
    """Adapter for OpenAI Codex CLI in headless mode (codex exec)."""

    name = "codex"

    def build_command(self, prompt: str, cwd: str) -> list[str]:
        model = self.agent_config.get("model", "gpt-5.4")
        return [
            "codex",
            "exec",
            prompt,
            "--json",
            "-m",
            model,
            "-c",
            'model_reasoning_effort="xhigh"',
            "--dangerously-bypass-approvals-and-sandbox",
            "-C",
            cwd,
        ]

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        result = AgentResult(agent=self.name)

        if not stdout.strip():
            result.errors.append("No output from codex")
            return result

        # Codex --json outputs JSONL events
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
            return self._parse_events(events, result)

        # Fallback: plain text
        result.assistant_text = stdout
        result.bash_commands = self._extract_dku_commands(stdout)
        return result

    def _parse_events(self, events: list[dict], result: AgentResult) -> AgentResult:
        """Parse Codex JSONL events.

        Real Codex event format (observed from codex exec --json):
          {"type":"thread.started","thread_id":"..."}
          {"type":"turn.started"}
          {"type":"item.completed","item":{"type":"agent_message","text":"..."}}
          {"type":"item.started","item":{"type":"command_execution","command":"..."}}
          {"type":"item.completed","item":{"type":"command_execution","command":"...","exit_code":0}}
          {"type":"item.completed","item":{"type":"file_change","path":"...","content":"..."}}
          {"type":"turn.completed","usage":{"input_tokens":N,"output_tokens":N}}
        """
        text_parts = []

        for event in events:
            event_type = event.get("type", "")
            item = event.get("item", {})
            item_type = item.get("type", "")

            # Command execution (shell commands)
            if event_type == "item.completed" and item_type == "command_execution":
                cmd = item.get("command", "")
                if cmd:
                    # Codex wraps commands in shell: /bin/zsh -lc 'actual command'
                    actual = self._unwrap_shell_command(cmd)
                    result.bash_commands.append(actual)

            # Agent text messages
            elif event_type == "item.completed" and item_type == "agent_message":
                text = item.get("text", "")
                if text:
                    text_parts.append(text)

            # File changes
            elif event_type == "item.completed" and item_type == "file_change":
                path = item.get("path", "")
                if path:
                    result.file_writes.append(path)

            # File reads
            elif event_type == "item.completed" and item_type == "file_read":
                path = item.get("path", "")
                if path:
                    result.file_reads.append(path)

            # Turn completed — token usage
            elif event_type == "turn.completed":
                usage = event.get("usage", {})
                result.input_tokens += usage.get("input_tokens", 0)
                result.output_tokens += usage.get("output_tokens", 0)

        result.assistant_text = "\n".join(text_parts)

        # If no structured commands found, try extracting from text
        if not result.bash_commands:
            result.bash_commands = self._extract_dku_commands(result.assistant_text)

        return result

    def _unwrap_shell_command(self, cmd: str) -> str:
        """Unwrap Codex shell wrapper: /bin/zsh -lc 'actual command' -> actual command."""
        # Pattern: /bin/zsh -lc 'command' or /bin/bash -lc 'command'
        for prefix in ("/bin/zsh -lc '", "/bin/bash -lc '", "/bin/sh -c '"):
            if cmd.startswith(prefix) and cmd.endswith("'"):
                return cmd[len(prefix):-1]
        return cmd

    def _extract_dku_commands(self, text: str) -> list[str]:
        """Extract dku commands from plain text."""
        commands = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("dku "):
                commands.append(stripped)
            elif stripped.startswith("$ dku "):
                commands.append(stripped[2:])
        return commands
