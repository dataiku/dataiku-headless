"""Agent adapters for benchmark runners."""

from benchmark.agents.base import AgentResult, BaseAgent, DockerAgent
from benchmark.agents.claude import ClaudeCodeAgent
from benchmark.agents.codex import CodexAgent

__all__ = [
    "AgentResult",
    "BaseAgent",
    "DockerAgent",
    "ClaudeCodeAgent",
    "CodexAgent",
]
