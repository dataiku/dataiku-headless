# Contributing

## Setup

```bash
git clone https://github.com/dataiku/dku-headless.git
cd dku-headless
uv sync
uv run pre-commit install
uv run dku --help
```

Python 3.10+ and [uv](https://docs.astral.sh/uv/). Tests mock `DSSClient`, so no DSS instance is needed to run them.

## Local checks

Run before pushing (the pre-commit hooks cover most of this):

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run python scripts/check_quality_ratchet.py     # blocks new C901/E501/oversized-file debt
make audit                                          # dependency CVE + secret scan
make test-plugin                                    # only if MCP packaging changed
```

## Conventions

- **Commits and PR titles are conventional** (`feat:`, `fix:`, `docs:`, …) — CI lints both, and the release/version is cut from them. See [`.commitlintrc.json`](.commitlintrc.json).
- **One noun per file** in `commands/`. All output goes through `output.py` — command modules never import `rich` or print data directly.
- Fixed-choice flags are `click.Choice`-backed enums (`enums.py`), never inline string checks.
- Add tests for new code and bug fixes; update the relevant `docs/` or skill reference.

Branch from `main`, open a PR against `main`, and fill in the PR template.

## Security
