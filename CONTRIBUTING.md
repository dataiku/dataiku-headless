# Contributing to Dataiku Headless

Thanks for your interest in contributing!

## Code of conduct

We expect everyone participating in this project to be respectful, inclusive, and constructive. Harassment or abuse of any kind will not be tolerated. Please report unacceptable behaviour to **opensource@dataiku.com**.

## Quick Start

```bash
git clone https://github.com/dataiku/dataiku-headless.git
cd dataiku-headless
uv sync
uv run dku --help
uv run pytest -v
```

## Development

- Python 3.10+ required, [uv](https://docs.astral.sh/uv/) recommended
- Private repo — not on PyPI. Install from local clone only.
- Tests mock `DSSClient` — no real DSS instance needed
- All formatting goes through `output.py` — command modules never import `rich` directly
- One file per noun in `commands/`

## How can I contribute?

### Reporting bugs

Before opening a new issue:
1. Check you're on the latest version.
2. Search existing issues (open and closed) at [github.com/dataiku/dataiku-headless/issues](https://github.com/dataiku/dataiku-headless/issues).
3. If the bug involves a security risk, do **not** file a public issue — see [Security issues](#security-issues).

When opening a bug report, please use our [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml) and include:
- **Dataiku Headless version** (`dku --version`).
- **Python version** and **OS**.
- **DSS version**.
- **Reproduction steps** from a clean install.
- **Current vs. expected behaviour**.

### Suggesting enhancements

Feature requests should be opened in [GitHub Discussions](https://github.com/dataiku/dataiku-headless/discussions/new/choose), not Issues. Describe the problem you're trying to solve, not just the solution you have in mind.

### Your first code contribution

Unsure where to begin? Look for issues tagged:
- **`good first issue`** — small, well-scoped tasks.
- **`help wanted`** — issues we'd love help on.
- **`documentation`** — docs improvements are a great first PR.

### Other ways to contribute

You don't have to write code:
- **Triage issues** — reproduce bugs, ask for missing information.
- **Review pull requests** — even non-maintainer review is valuable.
- **Improve documentation** — the guides in `docs/` and skill references.
- **Answer questions** in Discussions.

## Workflow

1. Clone the repo (requires access)
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run tests: `uv run pytest -v`
5. Run lint: `uv run ruff check . && uv run ruff format --check .`
6. Commit with semantic messages (see below)
7. Open a PR against `main`

## Pull request checklist

Before submitting a PR, please confirm:

- [ ] You've branched from `main`.
- [ ] You've added tests for new code or bug fixes.
- [ ] You've updated relevant docs.
- [ ] `uv run pytest -v` passes locally.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass.
- [ ] Your commit messages and **PR title** follow [Conventional Commits](#commit-messages).
When opening the PR:
1. **Link the issue** it addresses (`Closes #123`) in the description.
2. **Keep PRs focused.** One logical change per PR.
3. **Mark it as a draft** if it isn't ready for review yet.
4. **Watch the CI checks** — fix any failures before requesting review.

## Quality Ratchet

CI runs a one-way quality gate (`scripts/check_quality_ratchet.py`) that tracks
Ruff `C901` (complexity) and `E501` (line-length) debt against
`quality/ruff-ratchet-baseline.json`. It fails only on **regressions** — a new
complex function, more long lines in a file, or a longer longest-line. Reducing
debt never fails the build.

If the gate fails and the change is intentional — or you moved code in a way
that legitimately shifts the counts — refresh the baseline and commit it:

```bash
uv run python scripts/check_quality_ratchet.py --write-baseline
```

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

## Security issues

**Please do not file public GitHub issues for security vulnerabilities.**

Email **opensource@dataiku.com** with details. We'll acknowledge receipt and coordinate disclosure with you.

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
