# Contributing to `dataiku-headless`

This file routes you to the right place. It deliberately restates nothing:
`AGENTS.md` and `CODING_STANDARDS_AND_STRUCTURE.md` are the sources of truth for
architecture, standards, and commands, and `RELEASE.md` for versioning.

## Where things belong

| You have | Take it to |
| --- | --- |
| A bug in a tool, skill, or the launcher | [New issue → Bug report](https://github.com/dataiku/dataiku-headless/issues/new?template=bug_report.yml) |
| An idea for a new tool, skill, or reference | [New issue → Feature or skill proposal](https://github.com/dataiku/dataiku-headless/issues/new?template=feature_request.yml) |
| A question about using Headless against a real instance | Slack `#ask-dataiku-headless`, not an issue |
| A change you have already written | A pull request, after reading the sections below |

File the issue before opening a PR for anything beyond a small fix. It is where
scope gets agreed, and `AGENTS.md` asks for the smallest coherent change.

## Before you write code

1. Read `AGENTS.md`. It defines the architecture, the module boundaries, and the
   rules for changing MCP code, Cobuild, launch/packaging, and skills.
2. Read `CODING_STANDARDS_AND_STRUCTURE.md`. It owns local setup, error handling,
   validation, async style, the Cobuild write-routing convention, the fixed tool
   surface, guardrails, and the PR checklist.
3. Read the files you will change and their tests.

## Proposing a skill change

Skills live under `skills/dataiku-headless/`. `SKILL.md` is the operator-facing
router; `references/` owns the per-object workflows. Route from intent to the
smallest relevant reference and keep the detail in the reference, not the router
— see *Changing skills or documentation* in `AGENTS.md`.

Update the root routing table only when routing actually changes.

## Proposing a tool change

New public tools are the exception, not the default. `AGENTS.md` names the
registration requirements: import the module in `dataiku_mcp/__init__.py`, and
update `tests/test_tool_surface.py` in the same change for every add, remove, or
rename. Writes to project-level flow and analytic assets go through Cobuild
unless they fall under a documented exception in the Cobuild Write-Routing
Convention in `CODING_STANDARDS_AND_STRUCTURE.md`.

## Commits and PR titles

Commits and PR titles use [Conventional Commits](https://www.conventionalcommits.org/).
Commitizen enforces both — commit messages via the `commit-msg` hook in
`.pre-commit-config.yaml`, and the PR title via
`.github/workflows/pr-title.yml`, which validates the squash-merge title with
`cz check`. A non-conforming title fails the required check.

Commit types are load-bearing because they drive the version bump. See
*Commit Messages* in `CODING_STANDARDS_AND_STRUCTURE.md` and `RELEASE.md`.

## Verification gates

Run the gates from the *Verification* section of `AGENTS.md` before handoff.
`.github/workflows/ci.yml` runs the same pre-commit hooks, the pytest matrix, and
a package build on every PR. No live Dataiku instance is required.

If a gate could not run, say which one and why in the PR description. Do not
claim full validation when only targeted tests ran.

## Pull requests

Forking is currently disabled on this repository, so push a branch here and open
the PR against `main`. If you cannot push a branch, ask in
`#ask-dataiku-headless`. Work through the PR checklist at the end of
`CODING_STANDARDS_AND_STRUCTURE.md`. Summarize changed behavior and the tests you
actually ran.

Never commit secrets, credentials, exports, local configuration, or values
derived from a real Dataiku tenant — project keys, connection names, model IDs.
