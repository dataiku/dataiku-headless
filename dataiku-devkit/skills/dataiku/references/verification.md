# Verification & Cost Reference

## Per-Artifact Verification

Every artifact MUST be verified before considering the task done. DSS commands can succeed (exit 0) while producing empty datasets, broken schemas, or misconfigured recipes.

| What you built | How to verify | What to check |
|----------------|--------------|---------------|
| **Dataset upload** | `dku dataset head NAME -P PROJ -n 3` | Rows exist, columns correct, types not all string |
| **Recipe (any type)** | `dku dataset build OUTPUT --wait -P PROJ` then `dku dataset head OUTPUT -P PROJ -n 5` | Output has rows, schema matches expectations |
| **Full pipeline** | `dku job run --target LEAF -P PROJ --type RECURSIVE_BUILD --auto-update-schema --wait` then `dku dataset head LEAF -P PROJ` | Final output is populated, no schema mismatches |
| **Visual recipe config** | `dku recipe get-definition NAME -P PROJ -o json` | Verify join keys, aggregation columns, filter conditions |
| **Agent** | `dku agent status NAME -P PROJ` | Status is correct, LLM is assigned |
| **Agent tools** | `dku agent-tool list -P PROJ` | Tools are created AND attached to the agent |
| **Knowledge bank** | `dku knowledge search NAME --query "test" -P PROJ` | Returns results after build |
| **Plugin push** | `dku plugin get NAME -o json` | Version correct, code env assigned |
| **Dashboard/Chart** | `dku insight validate ID -P PROJ` | Column names exist in dataset |
| **Scenario** | `dku scenario run NAME -P PROJ --wait` then `dku scenario status NAME -P PROJ` | Completed successfully |
| **ML model** | `dku ml details AID TID MID -P PROJ` | Metrics exist, performance is reasonable |

**Key rules:**
1. `dku dataset head -o json` returning `[]` = 0 rows, not an error. Always check.
2. Never assume success from exit code alone.
3. For joins: check that column prefixing (customers_name, orders_amount) matches downstream refs.
4. Test agents end-to-end — creating agent + tools is not enough; verify the agent can call them.

---

## Cost Consciousness

Before triggering expensive operations, check cost risk:

| Action | Cost risk | What to check first |
|--------|-----------|-------------------|
| `RECURSIVE_BUILD` on large flow | **High** — rebuilds everything upstream | `dku flow visualize` to see scope; ask user |
| Python recipe on large dataset | **Medium** — loads data into memory | `dku dataset info` for row count; suggest sampling |
| LLM recipe (prompt, classify, embed) | **High** — API cost per row | `dku dataset info` for row count; estimate: rows × tokens × $/token |
| Building a knowledge bank | **Medium** — embedding cost per chunk | Check source dataset size |
| Visual recipe (join, group, sort) | **Low** — DSS-optimized, uses engines | Usually safe; check if Spark connection |
| Agent test query | **Low** — single LLM call | Safe for testing |
| Training ML model (AutoML) | **Medium** — CPU/GPU time | Check dataset size and algorithms enabled |

**LLM cost rules:**
- Prefer visual recipes over LLM recipes — a join costs zero tokens.
- Sample before LLM processing: create a 100-row sampling recipe to validate output format before running on full data.
- Use `dku llm list -P PROJ` to see available models. Classification/extraction tasks often work with smaller, cheaper models.
- **Never trigger a full recursive build without asking the user** when the project has Spark, BigQuery, or Snowflake connections.
