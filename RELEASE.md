# Releasing `dataiku-headless`

Feature PRs go into a release branch. When the batch is ready, update its
version, merge it into `main`, and publish it.

## Normal release checklist

These examples release **0.8.0**. Replace that version with your chosen version
throughout. Use a minor bump for new features (for example, `0.7.0` → `0.8.0`)
and a patch bump for fixes (`0.8.0` → `0.8.1`). The release branch name determines
the version the workflow will write.

Before your first release, an administrator must complete the
[one-time repository setup](#repository-setup-and-transition) below. Run these
commands from a clean checkout of this repository with `git` and `gh`
authenticated to GitHub.

### 1. Create the release branch

Start from the latest `main`, before adding new features:

```bash
git fetch origin
git switch -c release/0.8.0 origin/main
git push -u origin release/0.8.0
```

Keep one active feature release branch. If `release/0.8.0` already exists,
continue with it instead of creating it again.

### 2. Add features through PRs into the release branch

For each feature or fix, create a working branch from the latest release branch:

```bash
git fetch origin
git switch -c feat/my-feature origin/release/0.8.0
```

Make and commit your changes, then push and open the feature PR:

```bash
git push -u origin feat/my-feature
gh pr create --base release/0.8.0 --head feat/my-feature \
  --title 'feat: describe the feature'
```

Replace the example branch name and title with your own. After review and
passing checks, choose **Squash and merge**. Use titles such as `feat: add a
capability` or `fix: correct a bug` so the changelog can group the changes.
Repeat for each feature or fix in the batch.

**Do not update version files yet.** They keep the previous release's version
until the next step. Feature PRs target `release/0.8.0`, not `main`.

### 3. Prepare the version update

When the batch is ready, pause new feature merges and run:

```bash
gh workflow run bump.yml --ref main \
  -f operation=prepare \
  -f release_branch=release/0.8.0
```

Or use **Actions → Bump version → Run workflow**: select branch **main**,
operation **prepare**, and enter `release/0.8.0` as **release_branch**.

Open the workflow run and follow the PR link in its summary. This is the
**version-update PR**:

```text
prepare-release/0.8.0 → release/0.8.0
```

It updates the project version, plugin manifests, lockfile, and changelog.
Review those changes, select **Approve workflows to run** if prompted, and wait
for checks to pass. Then **Squash and merge** this PR into `release/0.8.0`.

### 4. Merge the release into main

Now open the **release PR**:

```bash
gh pr create --base main --head release/0.8.0 \
  --title 'bump: release 0.8.0'
```

This PR contains the whole batch:

```text
release/0.8.0 → main
```

Review it and wait for checks to pass. Choose **Create a merge commit**.
**Do not squash or rebase this PR.** If only squash is available, an admin must
enable merge commits before you proceed.

Write down this PR's number: you need it for publishing. It is **not** the
version-update PR number from step 3.

### 5. Publish the release

In **Actions → CI**, wait for the run on the release's merge commit on `main`
to pass. Then run the command below, replacing `123` with the **release PR
number from step 4**:

```bash
gh workflow run bump.yml --ref main \
  -f operation=publish \
  -f release_pr=123
```

Or use **Actions → Bump version → Run workflow**: select branch **main**,
operation **publish**, and enter that PR number as **release_pr**. Leave
**release_branch** empty for publication.

Wait for the workflow to succeed, then check **Releases** in GitHub. It creates
the `v0.8.0` GitHub release and both tags on the reviewed merge commit:

- `v0.8.0`
- `dataiku-headless--v0.8.0`

Nothing is published to PyPI. Merging the PR alone does not publish anything.

### 6. Clean up and start the next cycle

After successful publication, delete `release/0.8.0` and
`prepare-release/0.8.0` in GitHub if they have not already been deleted. Start
the next release branch from the latest `main` by repeating step 1 with the
next version.

### Which PR goes where?

| PR | Source → target | Merge method |
| --- | --- | --- |
| Feature or fix | Your working branch → `release/0.8.0` | Squash and merge |
| Version update (created by Prepare) | `prepare-release/0.8.0` → `release/0.8.0` | Squash and merge |
| Release (its number is used for Publish) | `release/0.8.0` → `main` | Create a merge commit |

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
  version-update PRs but never approves or merges them. No PAT or bypass is needed.

The repository was configured for squash merges only when this workflow was
written. A repository administrator must enable merge commits and configure the
required checks; these settings are not changed by merging this PR.

PRs created with `GITHUB_TOKEN` may require a maintainer to select **Approve
workflows to run** before CI starts. See
[GitHub's token documentation](https://docs.github.com/en/actions/concepts/security/github_token).
The old `RELEASE_ENABLED` variable is unused and can be removed. Both workflow
operations are dispatched from `main`.

## What the workflow checks

Preparation checks the previous version tag and requires current `main` to be
included in the release branch. Commitizen sets the version from the branch
name and generates notes from Conventional Commits. The workflow opens a PR;
it never pushes version changes directly into either protected branch.

Preparation also runs `uv lock --script runtime/run_mcp.py --upgrade` in the
runner. If this changes the runtime lockfile, update and test the lock through
a PR into the release branch before retrying preparation.

Publication checks successful CI on the exact main merge commit, verifies that
it preserves the release branch's history and contents, and validates versions,
locks, and notes before publishing. Later commits on `main` are not included.
The two tags are pushed together and existing tags are never moved. Retrying
publication reuses matching tags and leaves an existing GitHub release unchanged.

Tags record what shipped. Between steps 4 and 5, `main` briefly contains the
merged release before its tags and GitHub release exist.

If a late fix is needed after the version-update PR merges, add the fix and its
changelog entry through a PR into the release branch, then re-review the batch.
Do not run another version bump for the same release.

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
| Version-update branch exists | Use its existing PR; do not overwrite it. If PR creation failed, open it manually against the release branch. |
| Generated PR CI is waiting | Select **Approve workflows to run**. |
| Only squash merge is available | Ask an admin to enable merge commits before merging a release into main. |
| Publish fails on merge shape | Do not tag a squash/rebase merge. Reconcile the history with maintainers before retrying. |
| Publish fails on CI | Wait for or resolve CI on that exact main merge commit. |
| Tags exist but release creation failed | Retry publish with the same PR number. Matching tags are reused. |
| Tag points elsewhere | Investigate; the workflow never overwrites published history. |

Correct a bad published release with a new patch version. No prerelease path is
provided by this workflow.
