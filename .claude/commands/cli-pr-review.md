Review a dku-cli PR by running real integration tests on a live Dataiku DSS instance.

## What This Does

1. Reads the PR diff to understand what changed (CLI commands, skill docs, flags, error handling)
2. Spawns a **minimal-context subagent** that acts like a real agent using the skill + CLI
3. The subagent creates a test project, uploads data, and attempts the workflows affected by the PR
4. Reports what worked, what failed, and what was confusing from the agent's perspective
5. Cleans up the test project

## How to Use

```
/cli-pr-review <PR number or branch name or description of changes>
```

## Workflow

### Step 1: Fetch and understand the PR

Run `gh pr diff $ARGUMENTS` to get the diff (if `$ARGUMENTS` is a branch name, use `gh pr diff $(gh pr list --head $ARGUMENTS --json number -q '.[0].number')` or `git diff main...$ARGUMENTS`).

Identify:
- New/changed CLI commands and flags
- Skill doc changes (SKILL.md, references/)
- Error handling changes
- What agent workflows are affected

### Step 2: Design Test Scenarios

For each changed feature, design a realistic test scenario that an agent would encounter. Use stock/sales/customer data — simple CSVs that exercise the feature.

### Step 3: Spawn Integration Test Agent

Spawn a subagent with `subagent_type: "general-purpose"` and these constraints:

**The subagent MUST:**
- Start from `dataiku-mcp/skills/dku-cli/SKILL.md` (the router), drill into one playbook, and get exact flags from `--help` — the way a real agent does
- NOT read CLAUDE.md, recipe.py source, or test files (that's insider knowledge agents don't have)
- Create project `CLI_PR_TEST` on the live DSS instance (always authed, free to create/delete)
- Upload test CSV data
- Attempt the workflows using only `dku` CLI commands
- Build recipes and verify outputs with `dku dataset head`
- Delete the test project when done
- Report: what succeeded, what failed, what was confusing, what the skill didn't explain

**Subagent prompt template:**
```
You are testing the dku CLI as if you were an AI agent with no insider knowledge.

RULES:
- Read dataiku-mcp/skills/dku-cli/SKILL.md FIRST, then drill into one playbook and `--help` — this is your only guide
- Use ONLY `uv run dku` commands (the CLI under test)
- Do NOT read source code, CLAUDE.md, or test files
- The CLI is already authenticated to a Dataiku DSS sandbox instance

TASK:
1. Create project CLI_PR_TEST: `uv run dku project create CLI_PR_TEST --name "PR Test" --if-not-exists`
2. Create and upload test data (generate a CSV with columns relevant to the test)
3. <INSERT specific test scenarios derived from the PR diff>
4. Build each recipe and verify output with `dku dataset head`
5. Delete project: `uv run dku project delete CLI_PR_TEST --yes --confirm-name CLI_PR_TEST`

REPORT at the end:
- Which commands succeeded
- Which commands failed (include full error output)
- What was confusing or missing from the skill docs
- Whether the --help text was sufficient to figure out the command
```

### Step 4: Review Results

Based on the subagent's report:
- **Passed**: Feature works as an agent would use it
- **Failed - CLI bug**: Command doesn't work as documented
- **Failed - Skill gap**: Agent couldn't figure out the right command from the skill
- **Failed - Help gap**: --help text was misleading or incomplete
- **Confusing**: Agent got it eventually but wasted tokens on wrong approaches

### Step 5: Report

Produce a structured review:

```markdown
## PR Review: [title]

### Integration Test Results
| Test | Result | Notes |
|------|--------|-------|

### Issues Found
- [list of bugs, skill gaps, help text issues]

### Verdict
- [ ] Ready to merge
- [ ] Needs fixes (list what)
```

## Key Principles

- **The subagent is the test.** If it can't figure out the command from the skill + --help, a real agent won't either.
- **Real DSS, not mocks.** Unit tests miss payload format issues, property restrictions, and server-side validation.
- **Minimal context = honest test.** The subagent shouldn't know how the code works internally.
- **Clean up after yourself.** Always delete CLI_PR_TEST at the end. If the subagent exits early, run the delete command yourself.
