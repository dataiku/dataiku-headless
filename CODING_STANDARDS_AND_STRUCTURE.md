# CODING_STANDARDS_AND_STRUCTURE.md

## Scope
These rules apply when Claude Code (or another coding agent) is **contributing to this repository** — adding or modifying MCP tools, skills, prompts, or supporting infrastructure.

## Local Setup

```bash
# Requires Python 3.10+ and uv (https://docs.astral.sh/uv/)
uv sync  # creates .venv and installs the project with its dependencies
uv run pre-commit install --install-hooks  # enable pre-commit + commit-msg hooks
```

Pre-commit runs file hygiene, `ruff check`, and `uv-lock` before each commit, and
validates the commit message against Conventional Commits. The same hooks run in CI
(`.github/workflows/ci.yml`). Run them manually across the tree with
`uv run pre-commit run --all-files`.

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
| Project/dataset/folder/recipe/ML skills | `skills/**/SKILL.md` |
| Cobuild conversation tools | `dataiku_mcp/tools/cobuild.py` |

## Error Handling
- Prefer simple, readable tool handlers: keep top-level control flow short, avoid repeated Dataiku lookups, and use local helpers only when they improve clarity.
- Keep MCP as a thin adapter: validate behavior invariants at the boundary (for example non-empty required lists and allowed mode values), and let Dataiku validate deeper domain-specific constraints.
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

## Tool Metadata

- Give each tool a short human title and a one-line description of what it is for and when to reach for it.
- The tool catalog is re-sent to the model on every turn of every session, used or not. Keep workflow detail and safety rules in the relevant `skills/**/references/` guide, which loads on demand, and describe only parameters whose correct use a name and type cannot convey.
- Set `readOnlyHint`, `destructiveHint`, and `openWorldHint` explicitly, classified from the handler's actual code paths rather than its name. Omit `idempotentHint` where it cannot apply. A tool whose effect depends on a runtime argument is catalogued at its maximum possible effect.
- `destructiveHint` is true when the handler can remove or overwrite state the call does not itself carry: a delete, a file or dataset overwrite, a wholesale list or collection replacement, a null-clears-field patch, or an execution that rewrites its outputs. It is false when the operation only adds state or fails on conflict.
- `openWorldHint` is false throughout: a tool's reach is the one configured Dataiku instance and the local host, which is a closed domain. Reaching a third-party system *through* that instance — an external connection, an LLM provider — does not open it.
- Annotations are catalog-time labels for host UX. They are not authorization and never replace an argument check, a permission, or a confirmation policy.
- Give a fixed-value parameter a `Literal` so its allowed values ride in the schema, and drop the `require_allowed_value` check it replaces. Keep the check and describe the values in prose instead when it normalizes input (for example `.upper()`), since a `Literal` would reject values that work today, or when the value set is large enough that listing it in every catalog send costs more than a description.

## Cobuild Write-Routing Convention
- This server intentionally does not expose direct create/update/delete tools for in-project flow and analytic assets (recipes, ML analyses, dashboards, insights, agents, agent tools, scenarios, webapps, wiki articles, data quality rules, knowledge banks, semantic models, evaluation stores). Project-level building goes through `dataiku_mcp/tools/cobuild.py`'s Cobuild conversation tools instead. `set_container_exec_config` is the narrow, placement-only exception; all other changes stay with Cobuild.
- Do not add a new direct write tool for an in-project asset type beyond the fixed exceptions below. If a gap in Cobuild's coverage is found, note it in the relevant SKILL.md rather than adding an MCP write tool around it.
- A new direct write tool is only justified when the operation is cross-project, instance-level, or must happen before a project/Cobuild conversation exists. The fixed bootstrap exceptions are `create_project`, `create_upload_dataset`, `create_managed_folder`, `upload_file_to_managed_folder`, `write_project_library_file`, and `set_project_variables`; all but `create_project` write into a project, and each creates a container or carries local content rather than building logic. The other fixed exceptions are deterministic execution of existing assets (`build_datasets`, `run_recipe`, `run_scenario`, and `abort_job`, which stops an existing job) and deterministic container execution placement for an existing object (`set_container_exec_config`).

## Fixed Tool Surface

- `runtime/run_mcp.py` is the single launcher. It requires `--transport stdio` for the local plugin or `--transport http` for the authenticated Streamable HTTP deployment. Keep the transports explicitly selected and preserve the same registered tool catalog.
- Register one directly visible tool catalog. Do not add an MCP search mode.
- The registered set is the contract; `tests/test_tool_surface.py` pins the exact catalog. Any tool add/remove/rename updates that pinned set in the same change.

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
uv run --quiet --locked --script ./runtime/run_mcp.py --transport stdio  # exactly what every manifest runs
```

`uv` 0.12.0 or later is a runtime prerequisite for the plugin. **`runtime/run_mcp.py`** is the server entry point: its [PEP 723](https://peps.python.org/pep-0723/) inline metadata declares pinned dependencies and `requires-python`, so uv creates an isolated cached environment without a project install. `dataiku_mcp` is imported from the working tree, so source edits take effect immediately, while local edits to dependencies do not.

The launcher validates its arguments, loads the repository-root `.env` without
overriding real environment variables, and only then imports `dataiku_mcp`.
Direct package imports do not load `.env`; embedding callers own environment
setup before import.

**`runtime/launcher.sh`** is inactive legacy code retained for possible future fallback use. No manifest invokes it; do not re-enable it without explicitly reviewing the platform behavior and updating all manifests.

The inline metadata and its adjacent `runtime/run_mcp.py.lock` resolve independently of the project `uv.lock`. The `==` pins are the direct dependency constraints for plugin launches; the script lock records the complete direct and transitive resolution. Bump direct pins deliberately, then regenerate and commit the script lock with `uv lock --script runtime/run_mcp.py`. Every launcher uses `--locked`, so a stale or absent script lock fails before server startup rather than resolving on a user's machine.

The inline dependency list duplicates `[project].dependencies`; `tests/test_pep723_launcher.py` fails if the two drift apart.

Inspect the registered MCP server surface without starting a transport:

```bash
uv run fastmcp inspect dataiku_mcp/__init__.py:mcp --skip-env
```

## Commit Messages

This repo uses [Commitizen](https://commitizen-tools.github.io/commitizen/) with the Conventional Commits format — `type(scope): subject` (e.g. `feat(recipes): …`, `fix(mcp): …`, `chore: …`). Commitizen is installed via the `dev` dependency group (`uv sync`).

```bash
uv run cz commit                               # guided, interactive commit
uv run cz check --rev-range origin/main..HEAD  # validate your branch's messages
uv run cz bump --dry-run                       # preview the next version (writes nothing)
```

Commit *types* decide the version bump, so they are load-bearing: `feat:` cuts a minor, `fix:` a patch, and `docs:`/`chore:`/`ci:`/`refactor:`/`test:` cut nothing. You don't run `cz bump` yourself — `.github/workflows/bump.yml` does it on `main`, bumping `[project].version` (and the plugin manifests), updating `CHANGELOG.md`, tagging `vX.Y.Z`, and publishing the GitHub release. Nothing is published to PyPI. See `RELEASE.md` for the full picture.

## PR Checklist
- [ ] Changes are limited to intended scope
- [ ] Commit messages follow Conventional Commits (`uv run cz check`)
- [ ] Python syntax check passes (`py_compile` on all modified `.py` files)
- [ ] Relevant `SKILL.md` files updated if tool behavior or payloads changed
- [ ] No instance-specific values (project keys, model IDs, LLM IDs, connection names) introduced
- [ ] No sensitive data committed in skill files and JSON examples taken from real example object payloads
- [ ] `README.md` updated if tool count, setup steps, or usage changed
