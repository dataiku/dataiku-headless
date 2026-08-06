# Releasing `dataiku-headless`

Releases are automated with [Commitizen](https://commitizen-tools.github.io/commitizen/)
and GitHub Actions. In the normal case you don't run anything by hand: merge
[Conventional Commits](https://www.conventionalcommits.org/) to `main` and the
version bump, tag, changelog entry, and GitHub release happen on their own.

**Nothing is published to a package index.** `dataiku-headless` is not on PyPI
and isn't planned to be. It's consumed as a harness plugin (Claude Code, Codex,
Cortex Code, Cursor) or as a git checkout, so a release here is exactly three
artifacts:

| Artifact | Why it exists |
| --- | --- |
| `vX.Y.Z` git tag | Fixed point to check out, diff against, and report bugs against |
| `dataiku-headless--vX.Y.Z` git tag | The plugin release, in the form `claude plugin tag` produces — the commit a harness resolves a plugin install to |
| `CHANGELOG.md` entry | Human-readable history, generated from commit types |
| GitHub release | The published, browsable release notes |

The version number still matters even without an index: Commitizen keeps it in
lockstep across `pyproject.toml` and the plugin manifests (portable Agent Plugins
`plugin.json`, plus the Claude Code and Codex compatibility manifests), and the
manifest version is how a harness notices there's a newer plugin to install.
`bump.yml` verifies that lockstep held before it tags anything — a
`version_files` entry whose version string stops matching is skipped *silently*
by Commitizen, which would otherwise ship a release whose manifests still
advertise the old version.

---

## The pipeline at a glance

```
 PR merged to main
    │
    ▼
 bump.yml ── commitizen
    • derives the next version from the conventional commits
    • updates [project].version + the plugin manifests (version_files)
    • updates CHANGELOG.md, commits "bump: X → Y"
    • creates and pushes tag  vX.Y.Z
    • verifies the plugin manifests carry the new version
    • creates and pushes tag  dataiku-headless--vX.Y.Z
    • creates the GitHub release, notes = the new CHANGELOG section
```

`ci.yml` (pre-commit hooks + pytest on Python 3.10–3.14) runs on every push and
PR and is the gate before anything merges to `main`.

Before Commitizen can create a version, `bump.yml` also verifies the PEP 723
script lockfile is valid and refreshes it in the disposable runner. If the
latest allowed transitive dependency resolution differs from
`bin/run_mcp.py.lock`, the workflow fails before changing the version or
creating tags. Regenerate the lock, run the normal checks, and commit it in a
PR; direct dependencies remain deliberately pinned in `bin/run_mcp.py`.

### Workflow files

| File | Trigger | Does |
| --- | --- | --- |
| `.github/workflows/ci.yml` | push / PR to `main` | Pre-commit hooks + pytest matrix (3.10–3.14) |
| `.github/workflows/bump.yml` | push to `main`, manual dispatch | Commitizen bump + changelog + `vX.Y.Z` and `dataiku-headless--vX.Y.Z` tags + GitHub release |

---

## One-time setup

### 1. Enable bumping

`bump.yml` is currently gated on the repository variable **`RELEASE_ENABLED`**
being `true` (*Settings → Secrets and variables → Actions → Variables*). While
it's unset or `false` the job **skips** — pushes to `main` finish green but no
version is cut.

This gate is temporary; it exists so merges during the PR-backlog cleanup don't
each cut a version. Once `main` is known good, drop the `RELEASE_ENABLED` clause
from the job's `if:` and delete the variable.

### 2. Seed the first tag

The repo has **no tags**. Commitizen derives the next version by diffing against
the last tag, so seed the baseline once at the current version:

```bash
git tag v0.2.0        # match [project].version in pyproject.toml
git push origin v0.2.0
```

Without this, the first bump has no base to diff from.

### 3. Nothing else

No secrets, no deployment environments, no tokens to rotate. `bump.yml` runs on
the default `GITHUB_TOKEN` with `contents: write`. (Earlier revisions needed a
`RELEASE_PAT` so the pushed tag would trigger a publish workflow — refs pushed
with `GITHUB_TOKEN` don't start new workflow runs. With publishing gone there's
no downstream workflow to trigger, so the PAT was removed. If you ever add a
tag-triggered workflow, you'll need to reintroduce it.)

---

## Cutting a release (the default path)

1. **Land work with Conventional Commits.** The commit *types* decide the bump:

   | Commit | Result (while `0.x`, `major_version_zero`) |
   | --- | --- |
   | `fix: ...` | patch → `0.2.0` → `0.2.1` |
   | `feat: ...` | minor → `0.2.0` → `0.3.0` |
   | `feat!: ...` / `BREAKING CHANGE:` | minor while `0.x` (would be major at `1.x`) |
   | `docs:`, `chore:`, `ci:`, `refactor:`, `test:` | no release |

2. **Merge to `main`.** `ci.yml` must pass first.

3. **`bump.yml` runs automatically.** If there are releasable commits it bumps
   the version, updates `CHANGELOG.md`, commits `bump: X → Y`, pushes the
   `vX.Y.Z` tag, and publishes the GitHub release. Pushes with nothing to release
   are a no-op (they finish green).

That's it. Nothing is run locally.

> **Note:** the bump commit is pushed with `GITHUB_TOKEN`, so it does not
> retrigger `ci.yml` or `bump.yml`. That's intended — it's a version-only commit
> over an already-green tree.

### Forcing a bump manually

To trigger a bump without a new push (e.g. after enabling `RELEASE_ENABLED`),
run the **Bump version** workflow from *Actions → Bump version → Run workflow*,
or:

```bash
gh workflow run bump.yml
```

### Pre-releases

There is no pre-release path. Pre-releases only earned their keep when there was
an index to publish to (`pip install --pre`) — without one, "install the
pre-release" and "check out the tag or branch" are the same action. To try
unreleased work, point your harness at a checkout of the branch.

---

## Versioning notes

- **Version scheme** is [PEP 440](https://peps.python.org/pep-0440/); the source
  of truth is `[project].version` in `pyproject.toml`. Commitizen keeps the
  plugin manifests listed in `[tool.commitizen].version_files` in lockstep with
  it.
- **Tag format** is `v$version` (e.g. `v0.3.0`).
- **`0.x` versions**: `major_version_zero = true`, so breaking changes bump the
  *minor*, not the major, until you deliberately release `1.0.0`.
- **Tags are mutable here.** Nothing has been uploaded to an immutable index, so
  a bad release can be fixed by deleting the tag and release and re-cutting —
  unlike a PyPI upload, which can never be replaced.

---

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `bump.yml` skipped on a merge to `main` | Either `RELEASE_ENABLED` isn't `true`, or the head commit starts with `bump:`. Check the job's `if:` conditions in the run summary. |
| `bump.yml` fails: *"No tag matching configuration"* | No baseline tag. Do the [seed the first tag](#2-seed-the-first-tag) step. |
| `bump.yml` ran green but cut no version | No releasable commits since the last tag (only `docs:`/`chore:`/`ci:`/…). Expected — `no_raise: "3,21"` makes that a no-op. |
| The tag was created but no GitHub release appeared | The release step only runs when the tag actually changed during the run. Check the *Detect whether a bump happened* step's output. |
| A release was cut in error | Delete the GitHub release and the tag (`git push --delete origin vX.Y.Z`), revert the `bump:` commit, then re-cut. Nothing external needs undoing. |
| Want to skip a release for a `feat`/`fix` merge | You can't selectively skip once merged; commit non-releasing types (`chore:`, `docs:`) or squash accordingly before merging. |

---

## Quick reference

```bash
# Normal release: just merge conventional commits to main. Nothing to run.

# Force a bump:
gh workflow run bump.yml

# Preview the next version locally (no changes written):
uv run cz bump --dry-run
```
