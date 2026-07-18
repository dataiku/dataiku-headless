# CODING_STANDARDS_AND_STRUCTURE.md

## Scope
These rules apply when Claude Code (or another coding agent) is **contributing to this repository** — adding or modifying MCP tools, skills, prompts, or supporting infrastructure.

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
| Cobuild conversation tools + durable store | `dataiku_mcp/tools/cobuild.py`, `dataiku_mcp/tools/utils/conversation_store.py` |
| Project audit engine | `dataiku_mcp/tools/utils/audit_engine.py` (tool wrapper: `tools/project_audit.py`) |
| The agent skill | `dataiku-skills/dataiku-headless/**` (one skill: `SKILL.md`, `soul.md`, `playbooks/`, `references/`) |

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

## Tool Surface Convention
- There are no exposure modes. The server exposes ONE fixed supervisor surface, gated only by `DKU_MCP_TRANSPORT` (stdio vs streamable-http). `tests/test_smoke.py` holds the exact allow-list (`EXPECTED_NON_COBUILD` + `KNOWN_COBUILD`); any tool added, removed, or renamed must update that set on purpose. It is the guard — there is no `FULL_COBUILD_DISABLED_TOOLS` set anymore.
- This server intentionally does not expose direct create/update/delete tools for in-project assets (recipes, datasets, ML analyses, dashboards, agents, scenarios, etc.). Project-level building goes through `dataiku_mcp/tools/cobuild.py`'s Cobuild conversation tools instead.
- Do not add a new direct write tool for an in-project asset type. If a gap in Cobuild's coverage is found, note it in the skill rather than adding an MCP write tool around it. Full-CRUD per-object surfaces live in the agent-dev-kit upstream, not here.
- A new direct write is only justified when the operation is cross-project, instance-level, or must happen before a project/Cobuild conversation exists. The sanctioned exceptions are the four bootstrap writes (`create_project`, `create_upload_dataset`/`create_upload_dataset_from_rows`, `upload_file_to_managed_folder`, `write_project_library_file`) and the three direct executions of existing assets (`build_datasets`, `run_recipe`, `run_scenario`).

## Cobuild Durable Store & Retained Turns
- A Cobuild turn can run for minutes. `cobuild.py` runs the blocking turn in a daemon thread whose `Future` is retained across a client-side timeout, so a timeout returns control without dropping the work — `get_cobuild_turn_status` settles it later. Do not re-send on timeout; poll.
- Conversation metadata (owning instance, project, creation time, pending delete-confirmation id) persists to `conversations.json` under `DKU_MCP_STATE_DIR` via `conversation_store.py`, so `send_*` / `answer_*` / `list_cobuild_conversations` survive a restart. The in-memory dict is only a hot cache; the store is the source of truth. Resolve the state dir at call time (never cache it) and keep writes atomic (`mkstemp` + `os.replace`, `0600`) — a stored `pending_confirmation_id` authorizes a destructive delete.
- `allow_edit_project` is a per-message grant defaulting to `false`. Keep it that way: inspection and planning are read-only; a build grant is opt-in on the specific message that carries a requested change.

## Project Audit Engine
- `audit_engine.py` is read-only: metrics are read from cached values (never recomputed), row samples are bounded, and the flow-consistency check is time-bounded and degrades to `skip`. Nothing may mutate DSS.
- Every failing check must carry a `fix` re-pointed at this server's action model: a copy-paste Cobuild delegation prompt, or a named MCP tool (e.g. `build_datasets`) for the rare direct action. Never emit `dku` shell commands or any other harness's syntax — they are meaningless to the supervisor.

## Skills Contract
- There is exactly one skill: `dataiku-skills/dataiku-headless/`. Routing is by the `SKILL.md` frontmatter `description` — there is no separate root routing file. Judgment lives in `soul.md`, task recipes in `playbooks/`, facts in `references/`.
- `references/tool-index.md` is generated from the registered tool surface — never hand-edit it; regenerate it. The skill's internal reference links are validated by a link checker. Both run in CI, so a drifted tool-index or a broken cross-reference fails the build.

## Guardrails
- Do not hardcode instance-specific values (project keys, model IDs, LLM IDs, code env names, connection names) as defaults in tools or skills.
- Use snapshot corpora to learn structure and common key patterns, not tenant-specific values.
- Keep behavior changes minimal and explicit; preserve backward compatibility unless a bug or safety issue requires change.
- Avoid committing sensitive snapshot files if they contain internal identifiers.

## Validation

Lint and test before committing (both run in CI):

```bash
uv run ruff check .    # lint (rule set pinned in pyproject.toml)
uv run pytest          # smoke + surface + cobuild + context + audit tests, no live DSS needed
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
- [ ] Lint and tests pass (`uv run ruff check .`, `uv run pytest`)
- [ ] If the tool surface changed, `tests/test_smoke.py`'s allow-list and the generated tool-index were updated on purpose
- [ ] The `dataiku-headless` skill updated if tool behavior or payloads changed
- [ ] No instance-specific values (project keys, model IDs, LLM IDs, connection names) introduced
- [ ] No sensitive data committed in skill files and JSON examples taken from real example object payloads
- [ ] `README.md` updated if tool count, setup steps, or usage changed
