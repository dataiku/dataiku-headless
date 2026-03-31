"""Parse raw agent output into structured traces for analysis."""

from __future__ import annotations

import re

from benchmark.agents.base import AgentResult


def extract_dku_commands(result: AgentResult) -> list[str]:
    """Extract all dku CLI commands from bash commands in the trace.

    A single bash_command entry may contain multiple chained commands
    (e.g., "dku project list && dku dataset list -P PROJ1").
    This function splits them out.
    """
    dku_commands = []
    for cmd in result.bash_commands:
        # Split on && and ; to find individual commands
        parts = re.split(r"\s*(?:&&|;)\s*", cmd)
        for part in parts:
            part = part.strip()
            # Handle pipes — take the first command
            pipe_parts = part.split("|")
            first = pipe_parts[0].strip()
            if first.startswith("dku "):
                dku_commands.append(first)
            # Also check subshell / command substitution
            for match in re.finditer(r"dku\s+[\w\-]+(?:\s+[\w\-./\"']+)*", part):
                found = match.group(0).strip()
                if found not in dku_commands:
                    dku_commands.append(found)
    return dku_commands


def count_bash_calls_with_dku(result: AgentResult) -> int:
    """Count how many separate Bash tool calls contain dku commands.

    Used to check chaining: ideally related dku commands should be in a
    single bash call, not spread across multiple tool invocations.
    """
    count = 0
    for cmd in result.bash_commands:
        if "dku " in cmd:
            count += 1
    return count


def extract_skills_read(result: AgentResult) -> list[str]:
    """Extract skill reference docs that were read during the run."""
    skill_reads = []
    for path in result.file_reads:
        if "skills/" in path and path.endswith(".md"):
            skill_reads.append(path)
    return skill_reads


def parse_meta_feedback(result: AgentResult) -> dict | None:
    """Extract structured META-FEEDBACK from agent output.

    Returns a dict with keys: skill_helpful, commands_worked, commands_failed,
    commands_missing, confusing, python_fallback, help_text_gaps, suggestion.
    Returns None if no feedback block found.
    """
    text = result.assistant_text
    match = re.search(r"META-FEEDBACK:\s*\n(.*?)END-META-FEEDBACK", text, re.DOTALL)
    if not match:
        return None

    feedback = {}
    block = match.group(1)
    for line in block.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().rstrip(":")
        value = value.strip()
        # Strip leading [ and trailing ] for list-like values
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1].strip()
        feedback[key] = value
    return feedback if feedback else None


def summarize_trace(result: AgentResult) -> dict:
    """Produce a human-readable summary of what the agent did."""
    dku_cmds = extract_dku_commands(result)
    meta = parse_meta_feedback(result)
    return {
        "agent": result.agent,
        "dku_commands": dku_cmds,
        "dku_command_count": len(dku_cmds),
        "bash_calls_with_dku": count_bash_calls_with_dku(result),
        "skills_invoked": result.skill_invocations,
        "agents_spawned": [a.get("description", "") for a in result.agent_spawns],
        "files_read": len(result.file_reads),
        "files_written": len(result.file_writes),
        "skill_docs_read": extract_skills_read(result),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "duration_ms": result.duration_ms,
        "timed_out": result.timed_out,
        "errors": result.errors,
        "meta_feedback": meta,
    }
