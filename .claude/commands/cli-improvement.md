We are improving the Dataiku DevKit CLI and skills based on benchmark feedback. Plan fixes that make agents more performant.

## #1 Rule: Built-in DSS Features Before Python

Every benchmark issue should be evaluated first through this lens: **could a built-in DSS feature replace the Python code the agent wrote?**

| Priority | Use | Never use Python when... |
|----------|-----|--------------------------|
| 1 | Visual recipes (join, group, filter, sort, window…) | agent writes pd.merge / groupby / concat |
| 2 | GenAI recipes (embed, extract, LLM eval…) | recipe type exists |
| 3 | AutoML / visual ML | no custom architecture needed |
| 4 | Agents & Knowledge Banks | standard RAG / tool-calling |
| 5 | Scenarios & automation | no complex conditional logic |
| 6 | SQL recipes | logic is a plain query |
| 7 | Python/R recipes | **last resort only** |

## Workflow

1. **Read feedback** from a benchmark run (now produced by the external benchmark repo) provided in `$ARGUMENTS`
2. **Capability check** — for every Python recipe or custom code: could a built-in feature handle it?
3. **Categorize issues:**
   - **Built-in capability gaps** ← highest priority
   - CLI bugs / missing flags / error handling
   - Skill doc gaps (missing patterns, buried guidance)
   - Test gaps
   - Not actionable (platform limitations)
4. **For each gap**, determine the fix: skill doc change, CLI error message suggesting the built-in, new command/flag, or SKILL.md example
5. **For each CLI fix**, verify the `dataikuapi` method exists — read `src/dku_cli/commands/` and confirm against the installed `dataikuapi` source
6. **Plan changes** with file paths and diffs, ordered by agent impact

## Requirements

- **Grounded** — no invented APIs or flags. Verify against `dataikuapi` source
- **Descriptive** — error messages guide agents to the right next step
- **Idempotent** — safe re-runs where possible (`--if-not-exists`, clear conflict errors)
- **Composable** — commands chain with `&&`, JSON output via `-o json`

## Key Files

| File | Purpose |
|------|---------|
| `dataiku-mcp/skills/dku-cli/SKILL.md` | Agent-facing router: rules, capability→playbook map, reference map |
| `dataiku-mcp/skills/dku-cli/playbooks/` | Task-complete workflows (one per task family) |
| `dataiku-mcp/skills/dku-cli/references/` | Durable payload shapes, schemas, processor/param tables, safety |
| `dku <group> [command] --help` | Self-describing CLI: exact flags as JSON under `DKU_AGENT_HELP=1` |
| `src/dku_cli/commands/` | Command implementations |
| `src/dku_cli/errors.py` | Error handling |

## Output Format

Produce a plan with:
- **What the benchmark revealed** (1–3 sentences)
- **Built-in Capability Wins** table: Python pattern → DSS alternative → fix needed
- **Ordered change list** with file paths, diffs, and dependencies
- **Verification steps** (`uv run pytest -v`, `--help` checks)
