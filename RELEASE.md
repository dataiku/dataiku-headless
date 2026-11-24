# Releasing `dataiku-headless`

Feature PRs go into a release branch. When the batch is ready, update its
version and merge it into `main`. Successful main CI publishes it automatically.

## Normal release checklist

The commands below use `X.Y.Z` as a version placeholder. Replace it with the
chosen release version before running them. Contributors should use the active
release branch; list existing branches with `git ls-remote --heads origin 'release/*'`
or ask a maintainer which one to target. Use a minor bump for new features (for
example, `0.7.0` → `0.8.0`) and a patch bump for fixes (`0.8.0` → `0.8.1`). The
release branch name determines the version the finalization command writes.

Before your first release, have an administrator verify the
[repository settings](#repository-settings) below. Run these commands from a
clean checkout of this repository with `git` and `gh`
authenticated to GitHub.

### 1. Create the release branch

Start from the latest `main`, before adding new features:

```bash
git fetch origin
git switch -c release/X.Y.Z origin/main
git push -u origin release/X.Y.Z
```

Keep one active feature release branch. If `release/X.Y.Z` already exists,
continue with it instead of creating it again.

### 2. Add features through PRs into the release branch

For each feature or fix, create a working branch from the latest release branch:

```bash
git fetch origin
git switch -c feat/my-feature origin/release/X.Y.Z
```

Make and commit your changes, then push and open the feature PR:

```bash
git push -u origin feat/my-feature
gh pr create --base release/X.Y.Z --head feat/my-feature \
  --title 'feat: describe the feature'
```

Replace the example branch name and title with your own. After review and
passing checks, choose **Squash and merge**. Use titles such as `feat: add a
capability` or `fix: correct a bug` so the changelog can group the changes.
Repeat for each feature or fix in the batch. For the last PR, complete step 3
before merging.

**Do not update version files yet.** They keep the previous release's version
until the next step. Feature PRs target `release/X.Y.Z`, not `main`.

### 3. Finalize in the last feature or fix PR

Pause other merges into the release branch. On your final feature/fix working
branch, include the latest `origin/main` and `origin/release/X.Y.Z`, and commit
your feature changes with Conventional Commit messages. Then run from the
repository root:

```bash
uv run python scripts/finalize_release.py release/X.Y.Z
```

The command fetches origin, verifies the branch and committed lockfiles, updates
the project and plugin versions, refreshes the unpublished changelog section,
and updates `uv.lock`. It leaves those changes in your worktree. It does not
create a branch, commit, PR, or tag, and does not push.

Review the diff, run the contributor checks, and include the generated files in
the same feature/fix PR:

```bash
git add -u
git commit -m 'bump: finalize X.Y.Z'
git push
```

After review and passing checks, **Squash and merge** that PR into
`release/X.Y.Z`. There is no separate version-update PR or preparation dispatch.
If changes land before the release merges into main, bring them into your
working branch, commit them, and rerun the command to refresh the notes. It
replaces the target version's generated section while preserving released
history; review any manual edits to unpublished notes after refreshing.

### 4. Merge the release into main

Now open the **release PR**:

```bash
gh pr create --base main --head release/X.Y.Z \
  --title 'bump: release X.Y.Z'
```

This PR contains the whole batch:

```text
release/X.Y.Z → main
```

Review it and wait for checks to pass. Choose **Create a merge commit**.
**Do not squash or rebase this PR.** If only squash is available, an admin must
enable merge commits before you proceed.

### 5. Publication runs automatically

After the release PR merges, **CI** runs on its exact merge commit. When CI
succeeds, **Release** finds the merged release PR and publishes `vX.Y.Z` with
both tags on that commit:

- `vX.Y.Z`
- `dataiku-headless--vX.Y.Z`

There is no second workflow dispatch or PR number to copy. Failed or cancelled
CI does not publish. For a transient failure or cancellation, rerun CI on that
exact merge commit. Fixes that change code need another reviewed release PR.
Check **Actions → Release** for the publication result and release link. Nothing
is published to PyPI.

### 6. Clean up and start the next cycle

After successful publication, delete `release/X.Y.Z` in GitHub. Start
the next release branch from the latest `main` by repeating step 1 with the
next version.

### Which PR goes where?

| PR | Source → target | Merge method |
| --- | --- | --- |
| Feature or fix (last one includes version/changelog updates) | Your working branch → `release/X.Y.Z` | Squash and merge |
| Release (publishes after main CI) | `release/X.Y.Z` → `main` | Create a merge commit |
| Synchronize main into a release | Working branch containing `main` → `release/X.Y.Z` | Create a merge commit |

## Repository settings

An administrator should verify these settings. Workflow files do not configure
branch protection or repository permissions:

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
  linear-history requirements on `main` and release branches so synchronization
  PRs can preserve ancestry too. If a ruleset offers allowed merge methods,
  restrict `main` to merge commits. Release branches need both squash merges
  for feature PRs and merge commits for synchronization PRs. Publication rejects
  a squash/rebase release merge.

Publication needs the workflow's declared contents-write, pull-request-read,
and Actions-read permissions. It does not create or approve PRs. Manual recovery
is dispatched from `main`. Automatic publication uses `workflow_run` after
successful push CI on main in this repository; the workflow must be on `main`
before automatic publication can run.

## What the release checks

Local finalization requires a clean feature/fix branch containing current main,
the target release branch, and the previous version tag. The target version must
be newer than main and must not already be tagged. Commitizen updates the
version files and generates release notes from committed Conventional Commits.
Rerunning for an unpublished target refreshes its notes without another bump.
Committed runtime dependencies are checked without upgrading them; dependency
upgrades belong in their own tested PRs.

The release PR's CI checks that its versions match `release/X.Y.Z` and that its
changelog section exists. Both protected branches receive changes through PRs.

Publication checks successful CI on the exact main merge commit, verifies that
it preserves the release branch's history and contents, and validates versions,
locks, and notes before publishing. Later commits on `main` are not included.
The two tags are pushed together and existing tags are never moved. Retrying
publication reuses matching tags and leaves an existing GitHub release unchanged.

Tags record what shipped. While main CI and publication run, `main` contains the
merged release before its tags and GitHub release exist.

If a late fix is needed before publication, include it through a PR into the
release branch and rerun local finalization there to refresh its notes. If the
release already merged into main, reconcile the history and use a newer patch
version. Do not modify published tags.

## Hotfixes and recovery

If automatic publication fails after CI succeeds, rerun the failed **Release**
run, or dispatch recovery from main with the merged **release PR** number
(`release/X.Y.Z → main`):

```bash
gh workflow run bump.yml --ref main -f release_pr=123
```

Recovery runs the same checks and reuses matching tags. For a failed main CI
run caused by a transient failure, rerun CI on the same commit first;
successful completion triggers publication again.

For an urgent patch while the next feature release is in progress, create
`release/X.Y.Z` for the patch from `main`, finalize in the fix PR, then
merge and let CI publish using the same process. Bring the patch release's main
commit into the active feature release branch through a synchronization PR
before its release. Choose **Create a merge commit** for that PR so `main`
remains an ancestor of the release branch. Squashing copies the changes but
does not preserve the ancestry required by finalization.

| Situation | Action |
| --- | --- |
| Manual recovery skipped | Dispatch recovery from `main`. |
| Automatic run skipped or reports no release PR | Only successful push CI on `main` for an exact merged release PR publishes. PR CI and ordinary main commits do not publish. |
| Target is not newer than main | Choose a newer release version. Already published versions cannot be finalized again. |
| Previous version tag is missing | Fetch tags and verify the previous release was published. Recover that publication before finalizing the next release. |
| Main is not an ancestor | Bring current main into the release branch through a synchronization PR using **Create a merge commit**, then retry finalization. |
| Worktree is dirty | Commit your feature changes or previous generated updates, then rerun local finalization. |
| Only squash merge is available | Ask an admin to enable merge commits before merging a release into main. |
| Publish fails on merge shape | Do not tag a squash/rebase merge. Reconcile the history with maintainers before retrying. |
| Publish fails on CI | For transient failures, rerun CI on the exact main merge commit. Successful CI triggers publication. Code fixes require another reviewed release PR. |
| Tags exist but release creation failed | Retry publish with the same PR number. Matching tags are reused. |
| Tag points elsewhere | Investigate; the workflow never overwrites published history. |

Correct a bad published release with a new patch version. No prerelease path is
provided by this workflow.
