# Releasing `dataiku-headless`

Collect feature and fix PRs on an existing `release/X.Y.Z` branch. Only release
branches merge into `main`. Finalize the batch with Commitizen, review and merge
the release, then manually publish its exact merge commit. Normal pushes and
merges never publish a release.

Each release has a changelog entry, a GitHub release, and two tags pointing to
the same commit: `vX.Y.Z` and `dataiku-headless--vX.Y.Z`. Nothing goes to PyPI.
Tags are the definitive record of what shipped; `main` is briefly ahead of the
latest tag between merging and publishing.

## Repository setup and transition

Merge the workflow change before enabling the new required source check. That
bootstrap PR is the last normal development PR into `main`; do not rename it to
a release branch or pretend it is a versioned release. Then configure:

- Protect `main` and `release/*` with required PR reviews and CI checks. Require
  branches to be up to date before merging, and dismiss stale reviews on new
  commits. Do not allow direct pushes or force pushes.
- On `main`, additionally require **Release branch into main** from the
  **Release source policy** workflow. It rejects sources other than a
  same-repository `release/X.Y.Z` branch. Its `pull_request_target` job executes
  no PR code and needs no token permissions. The check must be marked required
  in repository settings to block merges; adding YAML alone does not do that.
- Enable **Allow merge commits** in repository settings. Release PRs into
  `main` must use **Create a merge commit**, not squash or rebase. Disable any
  linear-history requirement on `main`; if a ruleset offers allowed merge
  methods, restrict `main` to merge commits. Squash can remain enabled for
  feature PRs into release branches. Publication rejects a squash/rebase merge.
- In **Settings → Actions → General → Workflow permissions**, enable **Allow
  GitHub Actions to create and approve pull requests**. The workflow creates
  finalization PRs but never approves or merges them. No PAT or bypass is needed.

The repository was configured for squash merges only when this workflow was
written. A repository administrator must enable merge commits and configure the
required checks; these settings are not changed by merging this PR.

PRs created with `GITHUB_TOKEN` may require a maintainer to select **Approve
workflows to run** before CI starts. See
[GitHub's token documentation](https://docs.github.com/en/actions/concepts/security/github_token).
The old `RELEASE_ENABLED` variable is unused and can be removed. Both workflow
operations are dispatched from `main`.

## Start and build a release

Create the branch from current `main` at the start of the cycle, before adding
features. For example:

```bash
git fetch origin
git switch -c release/0.8.0 origin/main
git push -u origin release/0.8.0
```

Keep one active feature release branch. Create working branches from it and
target feature/fix PRs at it. Squash those PRs using Conventional Commit titles
so Commitizen can generate useful release notes. CI and title validation run on
PRs targeting both `release/*` and `main`.

The release branch initially keeps the previous published version. Its name
specifies the intended final version: `release/0.8.0` will become `0.8.0`.
Commitizen updates all configured manifests and generates the changelog from
conventional commits; it does not override the version chosen in the branch
name. `uv run cz bump --dry-run` offers a read-only version recommendation.

## Finalize the batch

Freeze new feature merges while preparing and reviewing the release. Ensure
current `main` is an ancestor of the release branch; bring any hotfixes forward
through a PR if needed. Then run **Bump version** on `main`, with **prepare** and
the existing release branch:

```bash
gh workflow run bump.yml --ref main -f operation=prepare -f release_branch=release/0.8.0
```

Preparation checks the previous version tag, target version, and runtime-lock
freshness, runs Commitizen locally without creating tags, updates `uv.lock`, and
validates every manifest and the changelog. It pushes `prepare-release/0.8.0`
and opens a finalization PR **into `release/0.8.0`**. Neither protected branch is
written directly. Approve the generated PR's workflows, review it, and merge it
after CI passes. A squash merge of this finalization PR is fine.

The freshness gate runs `uv lock --script runtime/run_mcp.py --upgrade` in the
runner. If it changes the script lock, update and test the lock through a PR
into the release branch before retrying. Publishing only validates reviewed
locks; it does not resolve newer dependencies.

Once finalized, open the release branch's PR into `main`:

```bash
gh pr create --base main --head release/0.8.0 --title 'bump: release 0.8.0'
```

Review the full batch and release notes. CI checks that the manifest version
matches the branch name and the changelog contains that version. Merge with
**Create a merge commit** to preserve feature/fix history. If a late fix enters
the batch, update the changelog through a PR and re-review the release before
merging; do not rerun the version bump on an already-finalized version.

## Publish

After CI passes on the release's main-branch merge commit, dispatch **publish**
with the release-to-main PR number, not the finalization PR number:

```bash
gh workflow run bump.yml --ref main -f operation=publish -f release_pr=123
```

Replace `123` with the actual PR number. Publication verifies the source branch,
main CI, and a two-parent merge commit whose second parent is the release PR's
head. Its tree must match the release branch, ensuring no extra main-only
changes slipped into the release. It checks versions, locks, and notes before
pushing either tag. Later main commits are not included.

Both tags are pushed atomically. Existing tags must resolve to the same SHA and
are never moved. The GitHub release uses that version's changelog section.
Retries leave an existing release unchanged; GitHub chooses whether a newly
created release is latest. Delete the release and finalization branches after
publication, then start the next cycle from `main`.

## Hotfixes and recovery

For an urgent patch while the next feature release is in progress, create
`release/X.Y.Z` for the patch from `main`, PR the fix into it, then finalize,
merge and publish using the same process. Bring the patch release's main
commit into the active feature release branch through a PR before its release.

| Situation | Action |
| --- | --- |
| Run skipped | Dispatch the workflow from `main`. |
| Target is not newer | The branch is already finalized or has the wrong version name. Open its release PR or choose the correct newer version. |
| Main is not an ancestor | Bring current main into the release branch through a PR before preparation. |
| Finalization branch exists | Use its existing PR; do not overwrite it. If PR creation failed, open it manually against the release branch. |
| Generated PR CI is waiting | Select **Approve workflows to run**. |
| Only squash merge is available | Ask an admin to enable merge commits before merging a release into main. |
| Publish fails on merge shape | Do not tag a squash/rebase merge. Reconcile the history with maintainers before retrying. |
| Publish fails on CI | Wait for or resolve CI on that exact main merge commit. |
| Tags exist but release creation failed | Retry publish with the same PR number. Matching tags are reused. |
| Tag points elsewhere | Investigate; the workflow never overwrites published history. |

Correct a bad published release with a new patch version. No prerelease path is
provided by this workflow.
