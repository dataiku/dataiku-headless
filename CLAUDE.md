# CLAUDE.md — Dataiku DevKit

## One Question

**Does this change make agents more successful?** Every CLI command, error message, and skill doc is judged by this.

## Development Workflow

When processing benchmark feedback:
1. **Capability check first** — Could a visual recipe, AutoML, or knowledge bank replace the Python the agent wrote? If yes, fix is in skill docs, not CLI code.
2. **Categorize**: built-in capability gap > CLI bug > skill doc gap > test gap > not actionable
3. **Fix in all three places** — CLI error message + `skills/dku-cli/SKILL.md` + CLAUDE.md gotcha
4. **Verify APIs** — Never invent `dataikuapi` methods. Read source in `.venv/lib/*/dataikuapi/`.
5. **Run tests** — `uv run pytest -v` (all must pass)
6. **Check `--help`** — `uv run dku <command> --help` must read well to an agent

## Project Structure

```
src/dku_cli/
├── main.py          # Root Typer app, global options, sub-command registration, whoami
├── helpers.py       # resolve_project(), get_client_from_ctx(), read_json_input(), resolve_agent()
├── output.py        # All rendering: render(), render_raw(), success()/error()/warn()/info()
├── errors.py        # dataikuapi exception → user-friendly message + exit code
├── client.py        # Auth resolution → DSSClient factory
├── auth.py          # Keyring + file fallback credential storage
├── config.py        # TOML config read/write via platformdirs
├── brand.py         # ◆ icon, version_string(), welcome()
└── commands/        # One file per noun (e.g. dataset.py, recipe.py, flow.py)

skills/
├── dku-cli/SKILL.md            # Primary agent interface — cheat sheet + gotchas
├── dku-cli/references/         # CLI command reference
├── dataiku/SKILL.md            # Platform knowledge router
└── dataiku/references/*.md     # 29 platform reference docs

benchmark/                      # 9-tier benchmark (192 scenarios)
docs/                           # command-api-mapping.md, block-graph-api.md
tests/                          # Unit tests (mock DSSClient, no real DSS)
```

## CLI Conventions

Pattern: every command follows `auth → project → dataikuapi call → output.py render`

- One file per noun in `commands/`. Named `{noun}.py` (except `auth_cmd.py`, `config_cmd.py`).
- All output via `output.py` — command modules never import `rich` directly.
- Auth via `helpers.get_client_from_ctx(ctx)`. Project via `helpers.resolve_project()`.
- `◆` icon must be wrapped: `[blue bold]◆[/blue bold]` — Typer strips bare unicode in help strings.
- **Error messages are prescriptive** — every `except` block must name the exact fix command. Use `exit_with_error()` with `details=[]` for multi-line guidance.
- **`--help` is documentation** — describe WHEN to use a command, not just WHAT it does. Include gotcha warnings in help text.
- Agent name/ID resolution via `helpers.resolve_agent()`: tries ID first, falls back to name match.
- Text input via `helpers.read_text_input(value)`: literal string, `@file.txt`, or stdin (`-`).

## Code Style

```bash
uv run ruff format .       # Format (run before committing)
uv run ruff check --fix .  # Lint + auto-fix
```

- Ruff defaults — no custom rules configured.
- Commits must follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, etc.) — enforced by commitlint pre-commit hook.

## Testing

```bash
uv run pytest -v    # All tests must pass
```

- `patch_client` fixture patches both `dku_cli.client.get_client` and `dku_cli.helpers.get_client`.
- Use `typer.testing.CliRunner`. Pass `--project PROJ1` instead of patching `resolve_project`.
- Test both table and JSON output modes.
- **Test error messages** — verify agents get prescriptive guidance on failure.

## Skill Quality Standards

When editing `skills/dku-cli/SKILL.md`:
- **Cheat sheet** (first 30 lines): one rule per line, prevents the top failure modes. Every new gotcha must have a matching cheat sheet rule.
- **Examples**: copy-paste-runnable — include `-P PROJ` and all required flags.
- **Gotchas table**: symptom → fix. Agents pattern-match on error messages.
- **Reference docs**: only deep knowledge not needed on every task. Don't bloat the skill.
