# Release

Releases go through a normal PR. Do not push release commits directly to
`main`.

## Cut a release

```bash
make release-pr
```

This command:

- starts from fresh `main`
- verifies the current version has a matching `vX.Y.Z` tag
- computes the next version from Conventional Commits
- creates `release/vX.Y.Z`
- runs `make release`
- pushes the branch
- opens a PR titled `chore(release): X.Y.Z`

Review and merge that PR. The Release workflow publishes after merge.

## What publishes

The Release workflow publishes only when the package version on `main` does not
already have a tag, or when a rerun sees that tag already pointing at the same
commit.

Normal changes can merge to `main` without bumping the version. They accumulate
until the next release PR.

## Artifacts

Release artifacts are:

- `dist/*.whl`
- `dist/*.tar.gz`
- `dataiku-mcp-bundle/dist/dataiku-mcp.mcpb`

Plugin manifests and the bundled `dataiku-mcp/wheels/` wheel are committed in
the release PR by `make release`.

Release notes are extracted from the generated `CHANGELOG.md` section for that
version.
