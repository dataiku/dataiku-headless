# Releasing `dataiku-headless`

Releases are prepared with [Commitizen](https://commitizen-tools.github.io/commitizen/)
and reviewed through a normal pull request. Merge
[Conventional Commits](https://www.conventionalcommits.org/) to `main`, then
manually run the preparation workflow when those changes should be released.

This document covers the one-time setup, the day-to-day flow, how to cut a
pre-release, and how to recover when something goes wrong.

---

## The pipeline at a glance

```
 Conventional PRs ── squash merge ──► main (changes accumulate)
                                              │
                                              ▼
 Run "Prepare release" ── Commitizen ──► release/vX.Y.Z PR
    • derives the next version from conventional commits
    • updates [project].version + plugin manifests + CHANGELOG.md
    • creates the release commit
                                              │
                                  review + merge
                                              ▼
 prepare-release.yml tags the exact merged commit as vX.Y.Z
                                              │
                                              ▼
 release.yml (trigger: vX.Y.Z tag)
    • lint + test + build + installed-wheel smoke
    • publishes to PyPI          (environment: pypi)
    • creates a GitHub release with changelog and artifacts
```

Pre-releases use the same reviewed preparation path:

```
 Run "Prepare release" with channel=prerelease
    • Commitizen prepares release/vX.Y.ZrcN
    • review and merge the release PR
    ▼
 pre-release.yml (trigger: vX.Y.ZrcN tag)
    • lint + test + build + installed-wheel smoke (once)
    • publishes to Test PyPI     (environment: testpypi)
    • publishes to PyPI          (environment: pypi)   → installable with `pip install --pre`
    • creates a GitHub pre-release with changelog and artifacts
```

`ci.yml` (lint + test on Python 3.10–3.14) runs on every push and PR and is the
gate before anything merges to `main`.

### Workflow files

| File                                    | Trigger                         | Does                                                         |
| --------------------------------------- | ------------------------------- | ------------------------------------------------------------ |
| `.github/workflows/ci.yml`              | push / PR to `main`             | Ruff lint + pytest matrix (3.10–3.14)                        |
| `.github/workflows/prepare-release.yml` | manual dispatch / version merge | Open release PR / tag its merged commit                      |
| `.github/workflows/release.yml`         | `vX.Y.Z` tag, manual dispatch   | Build + publish to **PyPI** + GitHub release                 |
| `.github/workflows/pre-release.yml`     | `vX.Y.ZrcN` tag, manual dispatch | Build + publish to **PyPI + Test PyPI** + GitHub pre-release |

---

## One-time setup

These must exist before the automation works. They only need to be done once.

### 1. Release GitHub App (required)

`prepare-release.yml` uses a GitHub App to open release PRs and push merged
release tags.
The default `GITHUB_TOKEN` is unsuitable because refs it pushes do not start the
publishing workflows.

Install the App on this repository with **Contents: read and write** and
**Pull requests: read and write**, then configure:

- repository variable `RELEASE_APP_ID`
- repository secret `RELEASE_APP_PRIVATE_KEY`

### 2. PyPI Trusted Publishing (OIDC)

Publishing uses [Trusted Publishing](https://docs.pypi.org/trusted-publishers/),
so **no API tokens are stored**. Configure a trusted publisher on each index:

| Index                        | Workflow filename      | Environment |
| ---------------------------- | ---------------------- | ----------- |
| <https://pypi.org>           | `release.yml`          | `pypi`      |
| <https://pypi.org>           | `pre-release.yml`      | `pypi`      |
| <https://test.pypi.org>      | `pre-release.yml`      | `testpypi`  |

For each: *Project → Publishing → Add a new pending/trusted publisher* with the
repository owner/name, the workflow filename, and the environment name above.
If the project doesn't exist on the index yet, add a **pending publisher** (or
do one manual token upload) to create it first.

> To fall back to API tokens instead of OIDC, set a `PYPI_API_TOKEN` /
> `TEST_PYPI_API_TOKEN` secret and uncomment the `password:` line in the
> relevant `Publish` step.

### 3. GitHub Environments

`pypi` and `testpypi` are referenced as deployment environments. They're
auto-created on first use; create them explicitly under *Settings →
Environments* if you want protection rules (e.g. required reviewers before a
publish).

### 4. Verify the baseline tag

Commitizen derives the next version by diffing against the tag matching the
current project version. Verify that tag exists before preparing a release:

```bash
git tag --list v0.2.0
```

If it is absent, restore it on the exact commit represented by version `0.2.0`;
do not tag the current tip blindly.

---

## Cutting a normal release (the default path)

1. **Land work with Conventional Commits.** The commit *types* decide the bump:

   | Commit                              | Result (while `0.x`, `major_version_zero`) |
   | ----------------------------------- | ------------------------------------------ |
   | `fix: ...`                          | patch → `0.2.0` → `0.2.1`                  |
   | `feat: ...`                         | minor → `0.2.0` → `0.3.0`                  |
   | `feat!: ...` / `BREAKING CHANGE:`   | minor while `0.x` (would be major at `1.x`) |
   | `docs:`, `chore:`, `ci:`, `refactor:`, `test:` | no release                      |

2. **Merge normal work to `main`.** Changes accumulate without publishing.

3. Run **Actions → Prepare release → Run workflow** with `channel=stable`, or:

```bash
gh workflow run prepare-release.yml -f channel=stable
```

4. Review the generated `release/vX.Y.Z` PR. Commitizen owns its version files,
   changelog, and release commit.

5. Merge the release PR after normal required CI passes and
   `RELEASE_ENABLED=true`. `prepare-release.yml` tags that exact merged commit;
   `release.yml` builds once, smoke-tests the wheel, publishes to **PyPI**, and
   creates the GitHub release with its artifacts.

---

## Cutting a pre-release

Run the same preparation workflow with the prerelease channel:

```bash
gh workflow run prepare-release.yml -f channel=prerelease
```

Commitizen prepares `X.Y.Zrc1` and increments subsequent release candidates.
Review and merge that release PR normally. `pre-release.yml` then builds once,
publishes the identical artifacts to **Test PyPI and PyPI**, and creates the
GitHub pre-release.

Install a published pre-release with:

```bash
pip install --pre dataiku-headless
```

Published versions are immutable. Workflow reruns skip an existing version so a
later failed step can recover without attempting to replace its files.

### Re-publishing an existing tag

Both `release.yml` and `pre-release.yml` accept a `workflow_dispatch` with a
`tag` input to re-run publishing for a tag that already exists (for example after
transient PyPI failures):

```bash
gh workflow run release.yml     -f tag=v0.3.0
gh workflow run pre-release.yml -f tag=v0.3.0rc1
```

`skip-existing: true` means a version already on the index is skipped rather than
failing the run, so re-runs are safe.

---

## Versioning notes

- **Version scheme** is [PEP 440](https://peps.python.org/pep-0440/); the source
  of truth is `[project].version` in `pyproject.toml`. Commitizen keeps the three
  plugin manifests (`.claude-plugin`, `.codex-plugin`, `.cursor-plugin`
  `plugin.json`) in lockstep via `[tool.commitizen].version_files`.
- **Tag format** is `v$version` (for example `v0.3.0` or `v0.3.0rc1`).
- **Prereleases** use Commitizen's canonical PEP 440 `rcN` spelling consistently
  in the project version, tag, artifact, and GitHub release.
- **`0.x` versions**: `major_version_zero = true`, so breaking changes bump the
  *minor*, not the major, until you deliberately release `1.0.0`.

---

## Troubleshooting

| Symptom                                                        | Cause / fix                                                                                     |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `prepare-release.yml` tagged a version but no publisher ran    | Confirm the release GitHub App credentials and that the tag matches `vX.Y.Z` or `vX.Y.ZrcN`. |
| `prepare-release.yml` fails: *"No tag matching configuration"* | No baseline tag. Do the [verify the baseline tag](#4-verify-the-baseline-tag) step.          |
| Merging the release PR fails: *"Releases are blocked"*         | `RELEASE_ENABLED` is not `true`. `prepare-release.yml` won't tag a version bump while it's unset, so nothing reaches `release.yml`/`pre-release.yml` either. |
| Publish step fails with an OIDC / *trusted publisher* error    | The PyPI trusted publisher isn't configured for that workflow + environment. See [Trusted Publishing](#2-pypi-trusted-publishing-oidc). |
| Publish says the version already exists                        | PyPI versions are immutable. Confirm the existing files belong to this release; otherwise prepare a new version. |
| Want to defer a release after merging a `feat`/`fix`           | Do nothing. Normal changes accumulate until someone runs **Prepare release**. |

---

## Quick reference

```bash
# Prepare a stable release PR:
gh workflow run prepare-release.yml -f channel=stable

# Prepare a pre-release PR:
gh workflow run prepare-release.yml -f channel=prerelease

# Re-publish an existing tag:
gh workflow run release.yml     -f tag=v0.3.0
gh workflow run pre-release.yml -f tag=v0.3.0rc1

# Preview the next version locally (no changes written):
uv run cz bump --dry-run
```
