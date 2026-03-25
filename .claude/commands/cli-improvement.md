We are working on improving Dataiku's DevKit skill & CLI through running various diverse benchmarking scenarios.

We just got feedback. Please plan to implement fixes that make sense for Claude Code & this DevKit to be more performant.

## #1 Priority: Built-in Capabilities First

**The single most important optimization is steering agents toward Dataiku's built-in capabilities instead of writing Python code.** DSS is a platform with 50+ visual recipes, AutoML, agents, knowledge banks, scenarios, and more. Python recipes are a last resort — not a default.

Every piece of benchmark feedback should be evaluated through this lens: **"Could this have been done with a built-in DSS feature instead of Python?"**

### Capability Hierarchy (most preferred → least preferred)

| Priority | Capability | Examples | Use Python instead? |
|----------|-----------|----------|---------------------|
| **1** | **Visual recipes** | join, group, stack, filter, sort, distinct, window, split, topn, prepare | NEVER — these always beat pd.merge/groupby/concat/filter |
| **2** | **GenAI recipes** | embed, embed-docs, extract, LLM eval, agent eval | Only if the recipe type doesn't exist for your use case |
| **3** | **Built-in models** | AutoML (visual ML), prediction, clustering, time series | Only for custom model architectures not in AutoML |
| **4** | **Agents & Knowledge Banks** | Visual agents, tools, RAG, knowledge banks | Only for custom agent logic beyond tool-calling |
| **5** | **Scenarios & automation** | Triggers, steps, reporters, metrics, checks | Only for complex conditional logic |
| **6** | **SQL recipes** | SQL query recipes, SQL notebook | When SQL expresses the logic more cleanly than visual |
| **7** | **Python/R recipes** | Custom transformations, API calls, ML scoring | **ONLY when nothing above fits** |

### What This Means for Fixes

When benchmark feedback shows an agent writing Python for something a visual recipe handles:
- The fix is in **skill docs** (`SKILL.md`, `references/`) — make the built-in option more prominent
- The fix may also be in **CLI error messages** — suggest the visual alternative when agents reach for Python unnecessarily
- The fix is NOT just "make the Python recipe work better" — that optimizes the wrong path

## Requirements

The CLI and skills should be **state of the art for agentic engineering**:

1. **Built-in first** — Skill docs and error messages must actively steer agents toward visual recipes, models, agents, and other built-in DSS features. Python is the escape hatch, not the default
2. **Descriptive** — Good helper functions and error messages that guide agents to the right next step (including suggesting built-in alternatives)
3. **Grounded** — All fixes must adhere to the Dataiku & Python API (`dataikuapi`) documentation. Do NOT invent APIs or flags that don't exist. Verify against `dataikuapi` source and `skills/dku-cli/references/commands.md`
4. **Idempotent** — Commands should support safe re-runs where possible (`--if-not-exists`, clear error messages on conflicts)
5. **Composable** — Commands chain cleanly with `&&`. Output is machine-parseable with `-o json`
6. **Agent-optimized** — Skill docs (`skills/dku-cli/SKILL.md`) surface critical patterns early so agents absorb them in the first pass

## Workflow

1. **Read the benchmark feedback** the user has pasted or referenced
2. **Capability check** — For every Python recipe or custom code the agent wrote, ask: could this be a visual recipe, model, agent, knowledge bank, scenario, or other built-in feature instead? Flag each as a "built-in capability gap"
3. **Categorize issues** into:
   - **Built-in capability gaps** — Agent used Python/custom code where a visual recipe, model, agent, or built-in feature would work. These are **highest priority**
   - **CLI code fixes** — Bugs, missing flags, error handling
   - **Skill doc improvements** — Missing patterns, unclear guidance, buried information
   - **Test gaps** — Missing test coverage
   - **Not actionable** — Platform limitations, edge cases
4. **For each built-in capability gap**, determine the fix:
   - Skill doc change to make the built-in option more prominent?
   - CLI error message that suggests the built-in alternative?
   - New CLI command or flag that makes the built-in path easier?
   - Example/template in SKILL.md showing the built-in approach?
5. **For each CLI fix**, verify the `dataikuapi` method exists and behaves as expected by reading `src/dku_cli/commands/` source and test files
6. **Plan changes** with specific file paths, line numbers, and code diffs
7. **Prioritize** by agent impact: how many benchmark tests does this fix unblock?

## Key files to read

- `benchmark/` — Test scenarios and results
- `skills/dku-cli/SKILL.md` — Agent-facing skill documentation (visual recipe guidance lives here)
- `skills/dataiku/SKILL.md` — Platform knowledge router (references to all built-in capabilities)
- `skills/dku-cli/references/commands.md` — Full CLI command reference
- `skills/dataiku/references/` — Platform reference docs (recipes, agents, models, scenarios, etc.)
- `src/dku_cli/commands/` — Command implementations
- `src/dku_cli/errors.py` — Error handling helpers
- `src/dku_cli/helpers.py` — Shared utilities
- `tests/` — Test suite (verify changes don't break existing tests)

## Output

Produce a plan with:
- **Context** section explaining what the benchmark revealed
- **Built-in Capability Wins** — Table showing where Python/custom code should be replaced with built-in DSS features, and what skill/CLI changes make that happen
- **Ordered list of changes** with file paths and code snippets
- Execution order (dependencies between changes)
- Verification steps (`uv run pytest -v`, `--help` output checks)

Here's the feedback — come up with a solid plan to resolve this and make our agents more performant:

$ARGUMENTS
