# Contributing to dataiku-headless

Thanks for your interest in contributing!

## Code of conduct

We expect everyone participating in this project to be respectful, inclusive, and constructive. Harassment or abuse of any kind will not be tolerated. Please report unacceptable behaviour to **opensource@dataiku.com**.

## Quick Start

```bash
git clone https://github.com/dataiku/dku-headless.git
cd dku-headless
uv sync                # create .venv and install with dependencies (Python 3.10+, uv)
uv run pytest -q       # smoke + surface + cobuild + context + audit tests; no live DSS needed
uv run ruff check .    # lint (rule set pinned in pyproject.toml)
```

## Development

- Python 3.10+ required, [uv](https://docs.astral.sh/uv/) recommended.
- Tests need **no live DSS instance** — they run against the registered tool surface and mocked behavior.
- The server exposes **one fixed supervisor surface**. There are no exposure modes; the only runtime trimming is transport gating (`DKU_MCP_TRANSPORT` = `stdio` vs `streamable-http`).
- The full architecture, tool-surface convention, write-routing rules, and skill contract live in [CODING_STANDARDS_AND_STRUCTURE.md](CODING_STANDARDS_AND_STRUCTURE.md). **Read it before changing tools or the skill** — this guide does not duplicate it.

### Skill-integrity scripts

The agent skill (`dataiku-skills/dataiku-headless/`) is kept honest by three scripts that also run in CI:

```bash
uv run python scripts/generate_tool_index.py   # regenerate references/tool-index.md from the live tool surface
uv run python scripts/check_skill_links.py      # frontmatter, routing completeness, dead file references
uv run python scripts/check_skill_tool_names.py # every tool-shaped token in the skill resolves to a real tool
```

`references/tool-index.md` is **generated** — never hand-edit it. If you change the tool surface, regenerate it and commit the result. A drifted tool-index, a broken cross-reference, or a reference to a non-existent tool fails the build.

### Changing the tool surface

The exact set of registered tools is pinned by an allow-list in `tests/test_smoke.py` (`EXPECTED_NON_COBUILD` + `KNOWN_COBUILD`). It is the guard: **any tool added, removed, or renamed must update that allow-list on purpose**, regenerate the tool-index, and update `README.md`'s tool counts. Do not add a direct create/update/delete tool for an in-project asset — project building goes through the Cobuild conversation tools. See CODING_STANDARDS_AND_STRUCTURE.md for the sanctioned bootstrap-write and direct-execution exceptions.

## How can I contribute?

### Reporting bugs

Before opening a new issue:
1. Check you're on the latest version.
2. Search existing issues (open and closed) at [github.com/dataiku/dku-headless/issues](https://github.com/dataiku/dku-headless/issues).
3. If the bug involves a security risk, do **not** file a public issue — see [Security issues](#security-issues).

When opening a bug report, please use our [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml) and include:
- **dataiku-headless version**.
- **Python version** and **OS**.
- **DSS version**.
- **Transport** (`stdio` or `streamable-http`) and **harness** (Claude Code / Codex / Cursor / OpenCode).
- **Reproduction steps** from a clean install.
- **Current vs. expected behaviour**.

### Suggesting enhancements

Feature requests should be opened in [GitHub Discussions](https://github.com/dataiku/dku-headless/discussions/new/choose), not Issues. Describe the problem you're trying to solve, not just the solution you have in mind.

### Other ways to contribute

You don't have to write code:
- **Triage issues** — reproduce bugs, ask for missing information.
- **Review pull requests** — even non-maintainer review is valuable.
- **Improve documentation** — the README, coding standards, and skill references.
- **Answer questions** in Discussions.

## Workflow

1. Clone the repo (requires access).
2. Create a feature branch: `git checkout -b feat/my-feature`.
3. Make your changes.
4. Run tests: `uv run pytest -q`.
5. Run lint: `uv run ruff check .`.
6. If you touched the skill or the tool surface, run the skill-integrity scripts (above).
7. Commit with Conventional Commit messages (see below).
8. Open a PR against `main`.

## Pull request checklist

Before submitting a PR, please confirm:

- [ ] You've branched from `main`.
- [ ] Changes are limited to intended scope.
- [ ] `uv run pytest -q` passes locally.
- [ ] `uv run ruff check .` passes.
- [ ] If the tool surface changed, `tests/test_smoke.py`'s allow-list and the generated tool-index were updated on purpose, and `README.md`'s tool counts were refreshed.
- [ ] The `dataiku-headless` skill was updated if tool behavior or payloads changed.
- [ ] No instance-specific values (project keys, model IDs, LLM IDs, connection names) introduced.
- [ ] Your commit messages and **PR title** follow [Conventional Commits](#commit-messages).

When opening the PR:
1. **Link the issue** it addresses (`Closes #123`) in the description.
2. **Keep PRs focused.** One logical change per PR.
3. **Mark it as a draft** if it isn't ready for review yet.
4. **Watch the CI checks** — fix any failures before requesting review.

## Commit messages

This repo uses [Commitizen](https://commitizen-tools.github.io/commitizen/) with the [Conventional Commits](https://www.conventionalcommits.org/) format — `type(scope): subject`:

```
feat(cobuild): retain in-flight turns across a client timeout
fix(mcp): redact secret-like connection values
docs: update README examples
chore: bump dependency versions
test: add audit-engine coverage
```

Commitizen is installed via the `dev` dependency group (`uv sync`). Releases are tagged `vX.Y.Z` (`tag_format = "v$version"`), and the version is bumped from commit history:

```bash
uv run cz check --rev-range origin/main..HEAD  # validate your branch's messages
uv run cz commit                               # guided, interactive commit
```

## Releasing

Maintainers cut a release from `main`:

1. Preview the next version: `uv run cz bump --dry-run`.
2. `uv run cz bump` — bumps `[project].version` and the three plugin manifests (via `version_files`), regenerates `CHANGELOG.md`, and creates the annotated `vX.Y.Z` tag from commit history.
3. `git push origin main --follow-tags` — pushes the commit and the tag together.
4. The `v*` tag triggers `.github/workflows/release.yml`, which re-runs the full gate (tests, lint, skill-integrity checks), builds the wheel and sdist, verifies the wheel version matches the tag, and publishes a GitHub Release with generated notes and the `dist/` artifacts.

## Security issues

**Please do not file public GitHub issues for security vulnerabilities.**

Email **opensource@dataiku.com** with details. We'll acknowledge receipt and coordinate disclosure with you.

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
