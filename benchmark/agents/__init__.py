"""Agent adapters for benchmark runners."""

from benchmark.agents.base import AgentResult, BaseAgent
from benchmark.agents.claude import ClaudeAgent
from benchmark.agents.codex import CodexAgent

__all__ = ["AgentResult", "BaseAgent", "ClaudeAgent", "CodexAgent"]
