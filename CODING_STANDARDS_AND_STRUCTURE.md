# CODING_STANDARDS_AND_STRUCTURE.md

## Scope
These rules apply when Claude Code (or another coding agent) is **contributing to this repository** — adding or modifying MCP tools, skills, prompts, or supporting infrastructure.

Always read @AGENTS.md for rules about operating Dataiku via the MCP server — inspecting projects, recipes, and ML pipelines, and driving Cobuild for project-level building.

## Local Setup

```bash
# Requires Python 3.10+ and uv (https://docs.astral.sh/uv/)
uv sync  # creates .venv and installs the project with its dependencies
```

Set environment variables:

```bash
export DKU_DSS_URL="https://your-instance.dataiku.com"
export DKU_API_KEY="your-api-key"
```

## Contribution Scope

| What to change | Where |
| --- | --- |
| MCP tool logic | `dataiku_mcp/tools/**/*.py` |
| Shared validation helpers | `dataiku_mcp/tools/utils/validation.py` |
| Workflow prompts | `dataiku_mcp/prompts/workflows.py` |
| Project/dataset/folder/recipe/ML skills | `dataiku-skills/**/SKILL.md` |
| Cobuild conversation tools | `dataiku_mcp/tools/cobuild.py` |

## Error Handling
- Prefer simple, readable tool handlers: keep top-level control flow short, avoid repeated DSS lookups, and use local helpers only when they improve clarity.
- Keep MCP as a thin adapter: validate behavior invariants at the boundary (for example non-empty required lists and allowed mode values), and let DSS validate deeper domain-specific constraints.
- For single-operation tools, prefer raising exceptions for invalid preconditions or missing objects instead of returning serialized `{"error": ...}` payloads.
- Reserve serialized per-item error payloads for APIs that intentionally support partial success (for example batch or multi-operation endpoints).
- Do not mix raised exceptions and serialized `{"error": ...}` responses for the same failure class within one tool.

## Tool Input Validation
- Assume FastMCP/Pydantic type validation for tool signatures; avoid duplicating type checks in tool code unless there is a clear compatibility/safety reason.
- Keep validation for structured inputs (JSON payloads/lists), enum-like parameters, and semantic risk parameters (`overwrite`, `drop_data`, replace modes, recursive build modes).
- Put reusable validation logic in `dataiku_mcp/tools/utils/validation.py` and reuse those helpers from tool modules instead of creating ad-hoc local validators.
- When reducing validation, preserve existing destructive-action safeguards and return clear errors from downstream API calls.

## Async And Blocking Style
- Prefer `async def` for MCP tool handlers.
- Keep blocking SDK/API calls fully inside `run_blocking(...)`.
- Prefer minimal blocking call wrappers (`await run_blocking(lambda: blocking_call(...))`) over nested local `_run` helpers when readability is improved.
- Prefer nested local `_run` helpers when the blocking logic is multi-step (branching, loops, error handling, or several intermediate values), even if a long lambda is possible.
- Keep data shaping/transformations outside `run_blocking(...)` unless they are expensive enough to justify offloading.
- Avoid evaluating SDK client construction/calls on the event loop thread before `run_blocking(...)`.

## MCP API Design
- Treat user confirmation as a harness concern (for example user-confirmation mode vs yolo mode in the caller).
- Do not add boolean confirmation flags (`confirm*`) to tool APIs; they are not reliable authorization boundaries for agent callers.
- Represent destructive intent through semantic operation parameters (for example `overwrite=true`, `drop_data=true`, `mode="replace"`, `job_type="RECURSIVE_FORCED_BUILD"`).

## Cobuild Write-Routing Convention
- This server intentionally does not expose direct create/update/delete tools for in-project assets (recipes, datasets, ML analyses, dashboards, agents, scenarios, etc.). Project-level building goes through `dataiku_mcp/tools/cobuild.py`'s Cobuild conversation tools instead.
- Do not add a new direct write tool for an in-project asset type. If a gap in Cobuild's coverage is found, note it in the relevant SKILL.md rather than adding an MCP write tool around it.
- A new direct write tool is only justified when the operation is cross-project, instance-level, or must happen before a project/Cobuild conversation exists (see the existing exceptions: `create_project`, `upload_file_to_managed_folder`, `write_project_library_file`, `create_upload_dataset`, `create_upload_dataset_from_rows`).
- If a tool module's write surface changes, update `config_mcp.py`'s `FULL_COBUILD_DISABLED_TOOLS` set to match (add newly-redundant read tools to it in `FULL` mode; do not add cross-project/instance tools to it — those stay enabled regardless of Cobuild mode).

## Guardrails
- Do not hardcode instance-specific values (project keys, model IDs, LLM IDs, code env names, connection names) as defaults in tools or skills.
- Use snapshot corpora to learn structure and common key patterns, not tenant-specific values.
- Keep behavior changes minimal and explicit; preserve backward compatibility unless a bug or safety issue requires change.
- Avoid committing sensitive snapshot files if they contain internal identifiers.

## Validation

Run a syntax check before committing Python changes:

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache uv run python -m py_compile $(find dataiku_mcp -name '*.py')
```

Run the MCP server locally to verify end-to-end:

```bash
./bin/run_mcp.sh
```

Inspect the MCP server interactively with MCP Inspector:

```bash
uv run --with "mcp[cli]" mcp dev -m dataiku_mcp
```

## Commit Messages

This repo uses [Commitizen](https://commitizen-tools.github.io/commitizen/) with the Conventional Commits format — `type(scope): subject` (e.g. `feat(recipes): …`, `fix(mcp): …`, `chore: …`). Commitizen is installed via the `dev` dependency group (`uv sync`).

```bash
uv run cz commit                               # guided, interactive commit
uv run cz check --rev-range origin/main..HEAD  # validate your branch's messages
uv run cz bump                                 # bump [project.version] + update CHANGELOG.md from history
```

`cz bump` derives the next version from the commit history and is configured (`[tool.commitizen]` in `pyproject.toml`) to read/write the version from `[project].version` and tag releases as `vX.Y.Z`.

## PR Checklist
- [ ] Changes are limited to intended scope
- [ ] Commit messages follow Conventional Commits (`uv run cz check`)
- [ ] Python syntax check passes (`py_compile` on all modified `.py` files)
- [ ] Relevant `SKILL.md` files updated if tool behavior or payloads changed
- [ ] No instance-specific values (project keys, model IDs, LLM IDs, connection names) introduced
- [ ] No sensitive data committed in skill files and JSON examples taken from real example object payloads
- [ ] `README.md` updated if tool count, setup steps, or usage changed
