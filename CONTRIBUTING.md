# Contributing to dku-cli

Thanks for your interest in contributing!

## Quick Start

```bash
git clone https://github.com/dataiku/dataiku-cli
cd dataiku-cli
uv sync
uv run dku --help
uv run pytest -v

# Install CLI + DevKit locally
uv tool install --from . dku-cli
./scripts/install-devkit.sh
```

## Development

- Python 3.10+ required, [uv](https://docs.astral.sh/uv/) recommended
- Private repo — not on PyPI. Install from local clone only.
- Tests mock `DSSClient` — no real DSS instance needed
- All formatting goes through `output.py` — command modules never import `rich` directly
- One file per noun in `commands/`

## Workflow

1. Clone the repo (requires access)
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run tests: `uv run pytest -v`
5. Commit with semantic messages (see below)
6. Open a PR against `main`

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new command group
fix: handle empty dataset schema
docs: update README examples
chore: bump dependency versions
test: add recipe creation tests
```

## Adding a Command

1. Create `src/dku_cli/commands/{noun}.py` with a `typer.Typer()` app
2. Register it in `main.py` via `app.add_typer()`
3. Use `helpers.get_client_from_ctx()` and `helpers.resolve_project()`
4. Format output via `output.py` (`render()`, `render_raw()`, `success()`)
5. Add tests in `tests/commands/test_{noun}.py`

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
