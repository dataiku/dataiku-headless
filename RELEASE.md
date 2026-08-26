# Releasing `dataiku-headless`

Releases use [Commitizen](https://commitizen-tools.github.io/) and two manually
dispatched GitHub Actions workflows. The release version always lands through a
normal pull request; publishing only tags an already-merged `main` commit.

**Nothing is published to a package index.** A release produces four artifacts:

| Artifact | Why it exists |
| --- | --- |
| Version bump commit | Updates the project and plugin-manifest versions plus `CHANGELOG.md` through normal review |
| `vX.Y.Z` tag | Fixed point for checkout, comparison, and bug reports |
| `dataiku-headless--vX.Y.Z` tag | Plugin release tag resolved by compatible plugin harnesses |
| GitHub release | Browsable release notes |

## Release flow

```text
Actions → Prepare release
    → release/vX.Y.Z pull request
    → merge to main through CI and branch protection
Actions → Publish release (X.Y.Z)
    → verify merged version, tags, and changelog
    → create both tags and the GitHub release
```

### 1. Prepare the release PR

Open **Actions → Prepare release → Run workflow**. Choose `auto` to derive the
increment from Conventional Commits, or explicitly choose `patch` or `minor`.
The workflow checks the committed PEP 723 script lockfile, runs Commitizen on a
new `release/vX.Y.Z` branch, and opens a PR with the version and changelog
changes. It does not push release tags.

The repository's **Settings → Actions → General → Workflow permissions** must
allow GitHub Actions to create pull requests. GitHub may mark the new PR's CI
run as awaiting approval; a collaborator with write access can approve it from
the PR before review and merge.

Merge that PR normally after CI passes. Do not manually change its generated
version fields or changelog section.

### 2. Publish the merged release

Open **Actions → Publish release → Run workflow** and enter the merged version
without the `v` prefix (for example, `0.4.0`). The workflow verifies that
`main`, all plugin manifests, and `CHANGELOG.md` agree on that version before
creating `vX.Y.Z`, `dataiku-headless--vX.Y.Z`, and the GitHub release.

It is safe to rerun Publish release after a partial failure: any existing tag
must already point at the current `main` commit, and an existing GitHub release
is left unchanged.

## Versioning

Commitizen uses Conventional Commits and PEP 440 versioning. While the project
is at `0.x`, both `feat:` and breaking changes produce a minor bump; `fix:`
produces a patch bump. `docs:`, `chore:`, `ci:`, `refactor:`, and `test:` do
not produce a release when `auto` is selected.

`pyproject.toml` is the source of truth. Commitizen keeps the configured plugin
manifests in lockstep, and Publish release rejects any drift.

## Dependency locks

The release workflows run `uv lock --script bin/run_mcp.py --check` to verify
the committed server lockfile. They deliberately do not run `--upgrade`:
transitive dependency refreshes belong in their own reviewed PRs, not in a
release attempt. The workflows pin UV to `0.12.6` so lock verification is
reproducible.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| Prepare release finds no next version | Merge a releasable Conventional Commit, or choose `patch`/`minor`. |
| A release branch already exists | Continue with its open PR, or close/delete it before preparing another release. |
| Publish release rejects the version | Merge the matching release PR first, then enter its version without `v`. |
| Publish release reports an existing tag at another commit | Stop and inspect it; do not move or replace tags without explicit release-owner approval. |
