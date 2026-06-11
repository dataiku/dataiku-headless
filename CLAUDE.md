# CLAUDE.md — Dataiku DevKit

## Tenet

Every change should answer: **does this make agents more successful?**

## Principles

An agent re-derives knowledge on every action — no memory between tasks, every cost paid every call.

- **Design for no memory.** Push into the surface (typed options, self-describing help, prescriptive errors) so the model never re-derives it.
- **Make the illegal unrepresentable, loudly.** Every fixed-choice set is an explicit enum. Bad input dies at parse time, not three steps later.
- **One fact, one home.** Help comes from `dku <cmd> --help` (always structured JSON). Docs explain *when and why*, never *how*. Nothing is written twice.
- **Good for agents = good for careful humans.** The agent is just less willing to paper over our mistakes.

## Code map

| File | Role | Rule |
|---|---|---|
| `spec.py` | `--help` — structured JSON help, scoped per command group | Never dump the whole tree: `dku --help` → groups, `dku recipe --help` → commands, `dku recipe X --help` → flag detail |
| `enums.py` | `_StrEnum` types wired to `click.Choice` | `case_sensitive=False` at parse, canonical case in payloads. Bad value → exit 2 + valid set. |
| `examples.py` | Per-command examples in agent help JSON | Only what the flag spec can't teach: payload shapes, repeatable flags, required combos, `@file`/stdin, KEY=VALUE syntax. No synopsis echoes. |
| `output.py` | Dense default: TSV lists, compact-JSON objects. `--format json\|csv\|ids\|quiet` to override | Data → stdout, always pipe-safe. Messages/hints/titles → stderr. |
| `errors.py` | Exception mapping | Always prescriptive text on stderr. Every `except` names the next command, pre-filled with ids. Not-found says what exists. |
| `safety.py` | Destructive ops guard | Exit 77. Tiers: READ/WRITE (unguarded) → DELETE (`--yes`) → CASCADE (`--yes` + `--confirm-name`) → ADMIN (plus `--i-know-what-im-doing`). |

## Adding a command

1. Check whether a built-in DSS feature already solves the workflow. If yes, stop.
2. Verify the `dataikuapi` method exists in `.venv/lib/*/dataikuapi/`. Never invent APIs.
3. Every fixed-choice set → `enum._StrEnum` → `click.Choice(case_sensitive=False)`.
4. Destructive commands must call `safety.guard(ctx, tier=..., action=..., subject=..., yes=...)`.
5. Every error path ends with a prescriptive next command.
6. Render through `output.render()` / `render_raw()` — never print data yourself. No per-command format flags; `--format` is global.
7. Add an example to `examples.py` only if the invocation is non-derivable from `--help` (JSON payload, repeatable flag, required combo, `@file`, KEY=VALUE). A `<command> <arg>` synopsis echo is noise — skip it.
8. Prefer zero-flag: `-P` + `DKU_PROJECT` covers the common case. Don't add redundant flags.
9. Tests: happy path (default TSV + `--format json`), error path (prescriptive message), `-P` resolution, safety guard (if destructive).

## What not to do

- No flag tables in markdown. Flags come from `dku <cmd> --help`.
- No inline validation. If you see `if x.upper() not in {...}`, replace it with `click.Choice`.
- No comments that explain what the code does. If it needs explanation, refactor.
- No flags that default to the only reasonable value.
- No blocking prompts, ever. `Use --yes to skip.`

## Skills layout

Skills live under `dataiku-mcp/skills/dku-cli/`. The structure is a map, not a manual:

| Layer | File | Purpose |
|---|---|---|
| Router | `SKILL.md` | DSS capability index + permanent rules. Thin — only enough to route the agent to one playbook. |
| Playbooks | `playbooks/*.md` | Task-complete walkthrough: steps, gotchas-with-fix, verification. One playbook per task type. |
| References | `references/*.md` | Cold detail — payload shapes, param tables, schemas. Opened only when a playbook directs. |

No flag tables in any layer. `dku <cmd> --help` is the sole source of flag truth.

## Quick start

```bash
uv sync && uv run pre-commit install
uv run pytest -v
uv run dku
```

Rebuild global install: `uv tool install --from . dku-cli --force --reinstall`
Rebuild MCP wheel: `make bundle` (in `dataiku-mcp/`)

## Testing

`uv run pytest -v && uv run ruff check . && uv run ruff format .`

CI runs Python 3.10–3.13. One-way quality ratchet in `scripts/check_quality_ratchet.py` (blocks *new* C901/E501 debt). Regenerate: `uv run python scripts/check_quality_ratchet.py --write-baseline`.

## Pull requests

Every PR: **What changed**, **Why**, **Agent impact** (what gets easier for agents), **Test plan** (unit + live DSS).

## Distribution

| Channel | Command |
|---|---|
| Direct install | `uv tool install git+https://github.com/dataiku/dataiku-cli.git` |
| Local dev | `uv tool install --from . dku-cli` |
| Claude Code | `/plugin marketplace add dataiku/dataiku-cli` |
| Codex | `codex plugin marketplace add dataiku/dataiku-cli` |
| OpenCode | `uv tool install --from git+…/dataiku-cli.git "dku-cli[mcp]"` + `dataiku-mcp/examples/opencode.json` |
| Claude Desktop | `.mcpb` bundle from `dataiku-mcp-bundle/` |

## Doc index

| Doc | When |
|---|---|
| `dataiku-mcp/skills/dku-cli/SKILL.md` | Start — DSS router + permanent rules |
| `dku <cmd> --help` | Exact flags/types/choices |
| `dataiku-mcp/skills/dku-cli/playbooks/` | Task walkthroughs, one per task |
| `dataiku-mcp/skills/dku-cli/references/` | Cold detail — payloads, safety tiers |
