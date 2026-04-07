"""Cost estimation for benchmark runs."""

from __future__ import annotations

# Default cost rates per 1K tokens (USD) — Claude Opus
DEFAULT_INPUT_RATE = 0.015
DEFAULT_OUTPUT_RATE = 0.075


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    input_rate: float = DEFAULT_INPUT_RATE,
    output_rate: float = DEFAULT_OUTPUT_RATE,
) -> float:
    """Estimate cost in USD from token counts and per-1K-token rates."""
    return (input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate)


def estimate_cost_from_config(
    input_tokens: int,
    output_tokens: int,
    agent_config: dict,
) -> float:
    """Estimate cost using rates from the agent's config section."""
    return estimate_cost(
        input_tokens,
        output_tokens,
        input_rate=agent_config.get("cost_per_1k_input", DEFAULT_INPUT_RATE),
        output_rate=agent_config.get("cost_per_1k_output", DEFAULT_OUTPUT_RATE),
    )
