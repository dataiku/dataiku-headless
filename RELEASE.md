# Releasing `dataiku-headless`

Batch normal PRs on `main`, then use **Bump version** (`bump.yml`) when the batch
is ready. The workflow retains Commitizen's version calculation and changelog
generation, but releases are manually initiated and version changes go through
a reviewed PR. Ordinary pushes and merges never publish a release.

Nothing is published to PyPI. Each release has a changelog entry, a GitHub
release, and two tags on the same commit:

- `vX.Y.Z`: the project version tag used by Commitizen.
- `dataiku-headless--vX.Y.Z`: the plugin release tag.

## One-time setup

The workflow uses the built-in `GITHUB_TOKEN`; no PAT or branch-protection
bypass is required. Keep the required reviews and CI checks on `main`.

In **Settings → Actions → General → Workflow permissions**, enable **Allow
GitHub Actions to create and approve pull requests**. An organization policy
may require an administrator to enable this. The workflow only creates PRs;
it does not approve or merge them.

PRs created using `GITHUB_TOKEN` require a person with write access to select
**Approve workflows to run** in the PR before its CI runs. See
[GitHub's token documentation](https://docs.github.com/en/actions/concepts/security/github_token).

The old `RELEASE_ENABLED` repository variable is no longer used. It can remain
`false` or be removed after this workflow is merged. Manual dispatch is the
release control.

## Prepare a batch

1. Merge the feature and fix PRs intended for this release into `main`.
2. Run **Actions → Bump version → Run workflow**, selecting branch `main` and
   operation **prepare**, or run:

   ```bash
   gh workflow run bump.yml --ref main -f operation=prepare
   ```

3. Follow the release PR link in the workflow summary. Approve its workflow
   runs, review the generated changelog and versions, and merge after CI passes.
   Squash merging with the generated `bump:` title is recommended.

Commitizen chooses the next version from commits since the previous version
tag: `fix:` produces a patch and `feat:` a minor; breaking changes produce a
minor while `major_version_zero` is enabled. A batch containing only
non-releasing commits such as `docs:` or `chore:` is a successful no-op.

Preparation checks the existing release baseline, refuses a second open
`release/*` PR, and preserves the existing runtime-lock freshness gate. It bumps
locally with `push: false`, updates `uv.lock`, and verifies every plugin manifest
against `pyproject.toml` and Commitizen's configured version files before
pushing a `release/X.Y.Z` branch. No release tags leave the runner at this stage.

The freshness gate runs `uv lock --script runtime/run_mcp.py --upgrade` in the
runner. If this changes the script lock, update and test that lock in a normal
PR before trying preparation again. Publishing validates the reviewed lock
without resolving newer dependencies.

## Publish the reviewed release

After the release PR is merged and **CI on its main-branch merge commit** passes,
run the workflow on `main` with operation **publish** and that PR's number:

```bash
gh workflow run bump.yml --ref main -f operation=publish -f release_pr=123
```

Replace `123` with the actual release PR number. Publishing verifies that the
PR came from this repository's `release/X.Y.Z` branch and merged into `main`.
It checks successful main CI, checks out the exact merge SHA, and validates
versions, lockfiles, and release notes before pushing either tag. Later commits
on `main` are not included. If main changed while the release PR was being
reviewed, review the resulting merge contents and changelog before publishing.

Both tags are pushed atomically. An existing tag must already resolve to the
same SHA; it is never moved. The GitHub release uses the matching changelog
section. GitHub determines whether it is the latest release, so a retry of an
older release does not explicitly promote it above a newer release.

After publication, delete the release branch if GitHub has not already done so.

## Recovery and troubleshooting

| Situation | Action |
| --- | --- |
| Run skipped | Dispatch from `main`; other refs cannot prepare or publish. |
| No new version | The batch has no releasable conventional commits. |
| Existing release PR | Finish it, or close it before preparing another batch. |
| Current project version has no tag | Publish the already-merged release PR before preparing another version. |
| Branch pushed but PR creation failed | Enable Actions PR creation, then open a PR from the existing `release/X.Y.Z` branch manually. Do not force-push over it. |
| Generated PR CI is waiting | Select **Approve workflows to run** on the PR. |
| Publish fails on CI | Wait for main CI on the release merge commit, or resolve its failure, then retry. |
| Tags exist but release creation failed | Re-run publish with the same PR number. Matching tags are reused. |
| Tag points elsewhere | Investigate; the workflow refuses to overwrite published history. |
| Existing GitHub release | A retry leaves it unchanged. If it is a draft, review and publish the draft explicitly. |

Correct a bad published release with a new patch version. Do not delete or move
release tags. No pre-release or maintenance-branch publishing path is provided
by this workflow.

For a read-only local preview:

```bash
uv run cz bump --dry-run
```
