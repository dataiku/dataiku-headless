# Releasing `dataiku-headless`

Releases are automated with [Commitizen](https://commitizen-tools.github.io/commitizen/)
and GitHub Actions. In the normal case you don't run anything by hand: merge
[Conventional Commits](https://www.conventionalcommits.org/) to `main` and a
version bump, tag, changelog entry, and PyPI publish happen on their own.

This document covers the one-time setup, the day-to-day flow, how to cut a
pre-release, and how to recover when something goes wrong.

---

## The pipeline at a glance

```
 PR merged to main
    │
    ▼
 bump.yml ── commitizen ──────────────────────────────────────────────┐
    • derives the next version from the conventional commits           │
    • updates [project].version + the plugin manifests (version_files) │
    • updates CHANGELOG.md, commits "bump: X → Y"                      │
    • creates and pushes tag  vX.Y.Z   (using RELEASE_PAT)             │
                                                                        │
    ┌───────────────────────────────────────────────────────────────── ┘
    ▼
 release.yml (trigger: vX.Y.Z tag)
    • stamps pyproject version from the tag
    • lint + test + build
    • publishes to PyPI          (environment: pypi)
    • creates a GitHub release   (vX.Y.Z)
```

Pre-releases are a separate, **manual** path:

```
 you push tag  vX.Y.Z.preN
    ▼
 pre-release.yml (trigger: vX.Y.Z.preN tag)
    • stamps pyproject version from the tag
    • lint + test + build (once)
    • publishes to Test PyPI     (environment: testpypi)
    • publishes to PyPI          (environment: pypi)   → installable with `pip install --pre`
    • creates a GitHub pre-release (vX.Y.Z.preN)
```

`ci.yml` (lint + test on Python 3.10–3.14) runs on every push and PR and is the
gate before anything merges to `main`.

### Workflow files

| File                          | Trigger                          | Does                                                    |
| ----------------------------- | -------------------------------- | ------------------------------------------------------- |
| `.github/workflows/ci.yml`          | push / PR to `main`              | Ruff lint + pytest matrix (3.10–3.14)                   |
| `.github/workflows/bump.yml`        | push to `main`, manual dispatch  | Commitizen bump + changelog + `vX.Y.Z` tag              |
| `.github/workflows/release.yml`     | `vX.Y.Z` tag, manual dispatch    | Build + publish to **PyPI** + GitHub release            |
| `.github/workflows/pre-release.yml` | `vX.Y.Z.preN` tag, manual dispatch | Build + publish to **PyPI + Test PyPI** + GitHub pre-release |

---

## One-time setup

These must exist before the automation works. They only need to be done once.

### 1. `RELEASE_PAT` secret (required)

`bump.yml` pushes the version-bump commit and the `vX.Y.Z` tag. It must push with
a **personal access token (or GitHub App token)**, *not* the default
`GITHUB_TOKEN` — refs pushed with `GITHUB_TOKEN` do **not** start new workflow
runs, so `release.yml` would never fire.

1. Create a token with `contents: write` on this repo:
   - Fine-grained PAT: *Repository access → this repo*, *Contents: Read and write*.
   - (Classic PAT: `repo` scope also works.)
2. Add it as a repository secret named **`RELEASE_PAT`**
   (*Settings → Secrets and variables → Actions → New repository secret*).

If the token expires, `bump.yml` will fail to push — rotate it the same way.

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

### 4. Seed the first tag

The repo currently has **no tags**. Commitizen derives the next version by
diffing against the last tag, so seed the baseline once at the current version:

```bash
git tag v0.2.0        # match [project].version in pyproject.toml
git push origin v0.2.0
```

Because `v0.2.0` already reflects what's published (or not), this baseline tag
just gives commitizen a starting point; the next bump goes from here.

---

## Cutting a normal release (the default path)

1. **Land work with Conventional Commits.** The commit *types* decide the bump:

   | Commit                              | Result (while `0.x`, `major_version_zero`) |
   | ----------------------------------- | ------------------------------------------ |
   | `fix: ...`                          | patch → `0.2.0` → `0.2.1`                  |
   | `feat: ...`                         | minor → `0.2.0` → `0.3.0`                  |
   | `feat!: ...` / `BREAKING CHANGE:`   | minor while `0.x` (would be major at `1.x`) |
   | `docs:`, `chore:`, `ci:`, `refactor:`, `test:` | no release                      |

2. **Merge to `main`.** `ci.yml` must pass first.

3. **`bump.yml` runs automatically.** If there are releasable commits it bumps
   the version, updates `CHANGELOG.md`, commits `bump: X → Y`, and pushes the
   `vX.Y.Z` tag. Pushes with nothing to release are a no-op (they finish green).

4. **`release.yml` runs on the new tag** — it re-runs lint + test, builds the
   sdist + wheel, publishes to **PyPI**, and creates the GitHub release. Watch it
   under the *Actions* tab.

That's it. Nothing is run locally.

### Forcing a bump manually

To trigger a bump without a new push (e.g. after fixing setup), run the
**Bump version** workflow from *Actions → Bump version → Run workflow*, or:

```bash
gh workflow run bump.yml
```

---

## Cutting a pre-release

Pre-releases are **not** produced by commitizen (see
[Versioning notes](#versioning-notes)); you cut them by hand.

```bash
# from the commit you want to ship (usually main):
git tag v0.3.0.pre1
git push origin v0.3.0.pre1
```

`pre-release.yml` then builds once and publishes to **both Test PyPI and PyPI**,
and creates a GitHub *pre-release*. The pushed tag is the source of truth for the
version — you do **not** bump `pyproject.toml`; the workflow stamps it from the
tag at build time.

Install a published pre-release with:

```bash
pip install --pre dataiku-headless
```

Increment the `preN` number for each subsequent pre-release (`v0.3.0.pre2`, …).

### Re-publishing an existing tag

Both `release.yml` and `pre-release.yml` accept a `workflow_dispatch` with a
`tag` input to re-run publishing for a tag that already exists (for example after
transient PyPI failures):

```bash
gh workflow run release.yml     -f tag=v0.3.0
gh workflow run pre-release.yml -f tag=v0.3.0.pre1
```

`skip-existing: true` means a version already on the index is skipped rather than
failing the run, so re-runs are safe.

---

## Versioning notes

- **Version scheme** is [PEP 440](https://peps.python.org/pep-0440/); the source
  of truth is `[project].version` in `pyproject.toml`. Commitizen keeps the three
  plugin manifests (`.claude-plugin`, `.codex-plugin`, `.cursor-plugin`
  `plugin.json`) in lockstep via `[tool.commitizen].version_files`.
- **Tag format** is `v$version` (e.g. `v0.3.0`).
- **`.preN` normalizes to `rcN` on PyPI.** A tag `v0.3.0.pre1` publishes the
  artifact as `0.3.0rc1` — the git tag and the package version differ by design.
- **Commitizen does not emit `.preN`.** `cz bump --prerelease` only produces
  `aN` / `bN` / `rcN`, which would not match `pre-release.yml`'s `vX.Y.Z.preN`
  trigger. This is why pre-releases are cut manually. If you'd rather have
  commitizen own pre-releases too, switch `pre-release.yml`'s trigger to the
  `rc`/`a`/`b` spelling and add a `prerelease` input to `bump.yml`.
- **`0.x` versions**: `major_version_zero = true`, so breaking changes bump the
  *minor*, not the major, until you deliberately release `1.0.0`.

---

## Troubleshooting

| Symptom                                                        | Cause / fix                                                                                     |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `bump.yml` tagged a version but `release.yml` never ran        | The tag was pushed with `GITHUB_TOKEN` instead of `RELEASE_PAT`. Check the secret exists and is valid. |
| `bump.yml` fails: *"No tag matching configuration"*            | No baseline tag. Do the [seed the first tag](#4-seed-the-first-tag) step.                       |
| `bump.yml` loops / re-runs on its own commit                   | Shouldn't happen — the job skips commits starting with `bump:`. Don't change the commitizen `bump_message` prefix. |
| Publish step fails with an OIDC / *trusted publisher* error    | The PyPI trusted publisher isn't configured for that workflow + environment. See [Trusted Publishing](#2-pypi-trusted-publishing-oidc). |
| Publish says the version already exists                        | Expected — `skip-existing` skips it. A version can never be re-uploaded to PyPI; cut a new version. |
| Want to skip a release for a `feat`/`fix` merge                | You can't selectively skip once merged; commit non-releasing types (`chore:`, `docs:`) or squash accordingly before merging. |

---

## Quick reference

```bash
# Normal release: just merge conventional commits to main. Nothing to run.

# Force a bump:
gh workflow run bump.yml

# Cut a pre-release:
git tag v0.3.0.pre1 && git push origin v0.3.0.pre1

# Re-publish an existing tag:
gh workflow run release.yml     -f tag=v0.3.0
gh workflow run pre-release.yml -f tag=v0.3.0.pre1

# Preview the next version locally (no changes written):
uv run cz bump --dry-run
```
