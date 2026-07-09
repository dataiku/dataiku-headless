---
name: block-reflection-reference
description: "Param matrix and canonical example for the REFLECTION block."
---

# REFLECTION Block

Runs a generator block, then applies a critique process. Three modes control how critique and synthesis work.

## Reflection Modes

| Mode | How it works |
|------|-------------|
| `CRITIQUE_AND_IMPROVE` | Generator runs → critique evaluates → feedback passed back to generator → repeats until approved or max iterations |
| `CRITIQUE_OR_RETRY` | Generator runs → critique evaluates → if rejected, generator restarts from scratch (no feedback passed) |
| `SYNTHESIZE` | Generator runs N times simultaneously in parallel threads → LLM consolidates all outputs into one result |

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"REFLECTION"` | |
| `mode` | yes | string | `"CRITIQUE_AND_IMPROVE"`, `"CRITIQUE_OR_RETRY"`, or `"SYNTHESIZE"` |
| `generatorBlockId` | yes | string | Block ID of the generator (usually an LLM_REQUEST) |
| `llmId` | yes | string | LLM for the critique/synthesis step — discover with `list_llms` |
| `expectationsPrompt` | yes | string | Instructions for the critique LLM |
| `critiqueCompletionSettings` | no | object | Completion settings for critique — supports `stopSequences`, `outputTrajectory`, `reasoningEffort` |
| `critiqueMaxIterations` | no | int | Max critique rounds (default 3) — CRITIQUE modes only |
| `failOnMaxIterations` | no | bool | Error if max iterations hit (default false) |
| `synthesizePrompt` | SYNTHESIZE only | string | Instructions for the synthesis LLM consolidating parallel outputs |
| `synthesizeCompletionSettings` | no | object | Completion settings for synthesis step |
| `synthesizeIterations` | no | int | Number of parallel generator runs — SYNTHESIZE mode only |
| `maxThreads` | no | int | Max parallel threads (default 32) |
| `streamOutput` | no | bool | Stream output to user |
| `outputMode` | no | string | `"ADD_TO_MESSAGES"`, `"SAVE_TO_STATE"`, or `"SAVE_TO_SCRATCHPAD"` |
| `outputStateKey` | no | string | State key when `outputMode` is `"SAVE_TO_STATE"` |
| `outputScratchpadKey` | no | string | Scratchpad key when `outputMode` is `"SAVE_TO_SCRATCHPAD"` |
| `nextBlock` | yes* | string | Next block after reflection completes |

## Critical Wiring Rule

**The reflection block manages its generator internally.** Wire the flow as:

```
previous_block → reflection_block → next_block
```

Do **NOT** wire:

```
previous_block → generator_block → reflection_block  ← WRONG
```

The generator block should not appear in the main flow chain. It is referenced by `generatorBlockId` and called internally by the reflection block.

## Canonical Example

```json
{
  "id": "reflect",
  "type": "REFLECTION",
  "mode": "CRITIQUE_AND_IMPROVE",
  "generatorBlockId": "draft_assessment",
  "llmId": "<llm_id>",
  "expectationsPrompt": "Review this assessment. Check that all data points are cited and the conclusion is justified. Approve if complete, reject with specific feedback if not.",
  "critiqueCompletionSettings": {"stopSequences": [], "outputTrajectory": true},
  "critiqueMaxIterations": 2,
  "failOnMaxIterations": false,
  "synthesizeCompletionSettings": {"stopSequences": [], "outputTrajectory": true},
  "synthesizeIterations": 3,
  "maxThreads": 32,
  "streamOutput": false,
  "outputMode": "ADD_TO_MESSAGES",
  "nextBlock": "compress"
}
```

## Guardrails

1. **Generator wiring** — see critical rule above. This was the most common mistake in testing.
2. **Critique sees conversation history**, not just the generated text. If the conversation has a greeting but the generator produced a detailed report, the critique may not see the report. Consider making the generator add output to messages.
3. **Keep `critiqueMaxIterations` low** (1-2) during development to avoid slow runs.
4. **`failOnMaxIterations: false`** lets the flow continue even if the critique never approves — useful for non-critical quality checks.
