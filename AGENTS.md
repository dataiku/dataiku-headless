# Contributor Guide

Use this file when changing this repository. It is not an operating guide for using Dataiku through the plugin; that workflow starts in `skills/dataiku-headless/SKILL.md`.

## Start here

- Read `CODING_STANDARDS_AND_STRUCTURE.md` before changing code. It owns the detailed design, validation, async, release, and review conventions.
- Read the files you will change, their tests, and the relevant skill reference before editing.
- Inspect the worktree first and preserve unrelated changes.
- Prefer the smallest coherent change. Do not add compatibility layers, new dependencies, or new public tools unless the task requires them.

## Architecture and boundaries

- `dataiku_mcp/` is a local, stdio-only FastMCP server. `dataiku_mcp/__init__.py` constructs the server and imports each tool module so decorators register their tools.
- `dataiku_mcp/tools/` contains thin adapters over the synchronous `dataikuapi` client. Shared authentication, validation, serialization, error, and executor helpers live under `dataiku_mcp/tools/utils/`.
- `dataiku_mcp/tools/cobuild.py` owns retained Cobuild conversations. Cobuild is the default path for constructing or modifying project-level flow and analytic assets.
- Cobuild owns construction and modification of project-level flow and analytic assets. Direct writes are allowed only for the fixed exception categories defined by the **Cobuild Write-Routing Convention** in `CODING_STANDARDS_AND_STRUCTURE.md`; do not infer permission for a new direct write from existing implementation.
- `skills/dataiku-headless/SKILL.md` is the operator-facing router. Its `references/` directory owns object-specific inspection, mutation, and verification workflows.
- `bin/launcher.sh` is the entry point used by manifests. It chooses a runtime and then executes the PEP 723 server script in `bin/run_mcp.py`. Stdout is reserved for MCP JSON-RPC; launcher and server diagnostics belong on stderr.

## Sources of truth

- Registered MCP surface: `tests/test_tool_surface.py`.
- Tool registration imports: `dataiku_mcp/__init__.py`.
- Project dependencies, Python support, version, and CLI entry points: `pyproject.toml`.
- Standalone server dependency pins and Python floor: the PEP 723 block in `bin/run_mcp.py`.
- Portable Agent Plugins package: root `plugin.json` + `mcp.json` (skills under `skills/`). Harness-specific launch config: `.mcp.json`, `.claude-plugin/plugin.json`, and `.codex-plugin/plugin.json`.
- User-facing installation and architecture overview: `README.md`.
- Release behavior: `RELEASE.md` and `.github/workflows/bump.yml`.
- CI behavior: `.github/workflows/ci.yml` and `.github/workflows/pr-title.yml`.

Do not copy volatile inventories, versions, or command details into this file when a source above can be referenced instead.

## Changing MCP code

- Keep tool handlers `async def`. Put every blocking SDK or filesystem operation inside `run_blocking(...)`; use `run_cobuild_blocking(...)` only for retained Cobuild turns.
- Capture any client or instance identity needed for consistency before the first `await` when a concurrent instance switch could otherwise change the target.
- Keep handlers thin: validate boundary invariants, call the SDK, shape a compact response, and let Dataiku validate deeper domain rules.
- Reuse helpers from `tools/utils/` instead of adding local variants. Use `compact_json`, `columnar`, and `omit_empty` for consistent responses where appropriate.
- Raise clear exceptions for whole-operation failures. Return structured per-item or uncertain-outcome payloads only when callers need partial results or durable job/run identities for recovery.
- Never return API keys, credentials, unredacted connection secrets, or sensitive exception text.
- Represent destructive intent with semantic parameters such as `overwrite`, `drop_data`, or a replace/run mode. Do not add `confirm*` parameters; confirmation is a harness concern.
- If adding a tool module, import it in `dataiku_mcp/__init__.py`. For every add, remove, or rename, update `tests/test_tool_surface.py` in the same change.
- Add focused tests with fakes or monkeypatching. Tests must not require a live Dataiku instance.

## Changing Cobuild, launch, or packaging code

- Preserve Cobuild conversation ownership by instance and project, one active turn per conversation, exact turn IDs for answers, and recoverable polling after timeouts or cancellation.
- Keep general SDK work and long-running Cobuild calls on their separate executors.
- Keep `bin/launcher.sh` POSIX `/bin/sh` compatible and silent on stdout.
- When runtime dependencies or the Python floor change, update both `pyproject.toml` and the PEP 723 block in `bin/run_mcp.py`; `tests/test_pep723_launcher.py` enforces their relationship.
- When manifest behavior changes, inspect every manifest rather than assuming their schemas or path interpolation rules are identical.
- When changing package contents or entry points, build the distributions and smoke-test the wheel as CI does.

## Changing skills or documentation

- Keep the root skill concise: route from user intent to the smallest relevant reference, then load detail on demand.
- Update the matching reference whenever a tool's arguments, response, safety rules, or recommended workflow changes. Update the root routing table only when routing changes.
- Preserve the operating model: inspect first, use Cobuild for project construction by default, use a documented direct exception when appropriate, and verify the resulting state.
- Do not invent project keys, object IDs, connection names, code environments, model IDs, or other instance-specific defaults. Never commit secrets or tenant-derived examples that identify a real environment.
- Update `README.md` when installation, launch behavior, user-visible capabilities, or the top-level structure changes. Avoid duplicating exhaustive tool catalogs in prose.

## Verification

Run the narrowest relevant tests while iterating, then run the repository gates before handoff:

```bash
uv sync --locked
uv run pre-commit run --all-files --show-diff-on-failure
uv run pytest
uv build
```

Useful focused checks include:

```bash
uv run pytest tests/test_tool_surface.py
uv run pytest tests/test_pep723_launcher.py
uv run pytest tests/test_agent_plugins.py
uv run pytest tests/test_cobuild.py
```

If a check is not relevant or cannot run, say exactly which check was skipped and why. A live Dataiku connection is not required for the automated suite.

## Pull requests and review

- Use Conventional Commits for commits and PR titles; Commitizen drives versioning. Validate branch commits with `uv run cz check --rev-range origin/main..HEAD` when applicable.
- Review for behavioral regressions, secret exposure, event-loop blocking, unsafe destructive defaults, stale skill guidance, tool-surface drift, and launcher/package drift.
- Keep generated caches, local configuration, exports, and credentials out of commits.
- Summarize changed behavior and tests run. Do not claim full validation when only targeted tests ran.
