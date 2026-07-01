# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- version list -->

## v0.5.0 (2026-07-01)

### Bug Fixes

- Address launch readiness review blockers
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- Doc enhancement ([#168](https://github.com/dataiku/dku-headless/pull/168),
  [`b7edeff`](https://github.com/dataiku/dku-headless/commit/b7edeffdae6a7032bf0296991c223f4a6ab8888e))

- Refresh bundled MCP wheel ([#168](https://github.com/dataiku/dku-headless/pull/168),
  [`b7edeff`](https://github.com/dataiku/dku-headless/commit/b7edeffdae6a7032bf0296991c223f4a6ab8888e))

- Refresh bundled plugin wheel ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- Remove OpenCode installation instructions and related dead links from documentation
  ([#168](https://github.com/dataiku/dku-headless/pull/168),
  [`b7edeff`](https://github.com/dataiku/dku-headless/commit/b7edeffdae6a7032bf0296991c223f4a6ab8888e))

- Remove outdated internal branding assets and styling guide
  ([#168](https://github.com/dataiku/dku-headless/pull/168),
  [`b7edeff`](https://github.com/dataiku/dku-headless/commit/b7edeffdae6a7032bf0296991c223f4a6ab8888e))

- Rename distribution to dku-headless ([#168](https://github.com/dataiku/dku-headless/pull/168),
  [`b7edeff`](https://github.com/dataiku/dku-headless/commit/b7edeffdae6a7032bf0296991c223f4a6ab8888e))

- Stabilize CLI help and release flow ([#238](https://github.com/dataiku/dku-headless/pull/238),
  [`fefc5e5`](https://github.com/dataiku/dku-headless/commit/fefc5e52be125df13a1cf7949986083036717549))

- Update exclude_commit_patterns to match conventional commit format
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- Update wheel ([#168](https://github.com/dataiku/dku-headless/pull/168),
  [`b7edeff`](https://github.com/dataiku/dku-headless/commit/b7edeffdae6a7032bf0296991c223f4a6ab8888e))

- Use valid code owner ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- V1 launch-blockers — git exit codes, MCP session safety, hosted dangerous-mode, honest docs
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **audit**: Flag empty default flow zones
  ([#221](https://github.com/dataiku/dku-headless/pull/221),
  [`ca022e6`](https://github.com/dataiku/dku-headless/commit/ca022e6718c3ed0bd49cb097a70e6727262c45eb))

- **auth**: Fall back to file store when keyring probing fails
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **build**: Scope schema-change reporting claim to --wait
  ([#198](https://github.com/dataiku/dku-headless/pull/198),
  [`69ecbe2`](https://github.com/dataiku/dku-headless/commit/69ecbe2ef005711b68dd9512f22b89507591b4f9))

- **cli**: Correctness & safety fixes across delete, scenario, SSO, plugin, git, recipe flags
  ([#174](https://github.com/dataiku/dku-headless/pull/174),
  [`5b78038`](https://github.com/dataiku/dku-headless/commit/5b7803887b99cc5899ec28176b3bcf6c57f8aa3c))

- **cli**: Handle typer vendored click errors
  ([#238](https://github.com/dataiku/dku-headless/pull/238),
  [`fefc5e5`](https://github.com/dataiku/dku-headless/commit/fefc5e52be125df13a1cf7949986083036717549))

- **cli**: Keep typer error fix within ratchet
  ([#238](https://github.com/dataiku/dku-headless/pull/238),
  [`fefc5e5`](https://github.com/dataiku/dku-headless/commit/fefc5e52be125df13a1cf7949986083036717549))

- **cli**: Repair evaluation recipe payloads
  ([#203](https://github.com/dataiku/dku-headless/pull/203),
  [`44fe8bc`](https://github.com/dataiku/dku-headless/commit/44fe8bc67d99236c3abb64794cfe63cd4dc7f865))

- **cli**: Stabilize help spec for latest typer
  ([#238](https://github.com/dataiku/dku-headless/pull/238),
  [`fefc5e5`](https://github.com/dataiku/dku-headless/commit/fefc5e52be125df13a1cf7949986083036717549))

- **codex**: Repair MCP plugin setup and package naming
  ([#168](https://github.com/dataiku/dku-headless/pull/168),
  [`b7edeff`](https://github.com/dataiku/dku-headless/commit/b7edeffdae6a7032bf0296991c223f4a6ab8888e))

- **dataset**: Restore set-meaning command and tests
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **git**: Exit non-zero when pull/push/fetch/switch fail
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **install**: Correct OpenCode/MCP install command + dead Discussion links
  ([#168](https://github.com/dataiku/dku-headless/pull/168),
  [`b7edeff`](https://github.com/dataiku/dku-headless/commit/b7edeffdae6a7032bf0296991c223f4a6ab8888e))

- **mcp**: Lock SessionStore and acquire sessions atomically
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **release**: Commit generated plugin assets
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **release**: Constrain FastMCP runtime major
  ([#238](https://github.com/dataiku/dku-headless/pull/238),
  [`fefc5e5`](https://github.com/dataiku/dku-headless/commit/fefc5e52be125df13a1cf7949986083036717549))

- **release**: Generate changelog in release PRs
  ([#238](https://github.com/dataiku/dku-headless/pull/238),
  [`fefc5e5`](https://github.com/dataiku/dku-headless/commit/fefc5e52be125df13a1cf7949986083036717549))

- **release**: Lock project before release commit
  ([#238](https://github.com/dataiku/dku-headless/pull/238),
  [`fefc5e5`](https://github.com/dataiku/dku-headless/commit/fefc5e52be125df13a1cf7949986083036717549))

- **release**: Psr build command ([#199](https://github.com/dataiku/dku-headless/pull/199),
  [`368e488`](https://github.com/dataiku/dku-headless/commit/368e48873747016b65a8469a2708fafccc7905dc))

- **release**: Remove pypi publish path ([#200](https://github.com/dataiku/dku-headless/pull/200),
  [`9bb90bd`](https://github.com/dataiku/dku-headless/commit/9bb90bd250ddbdcfc4ace11f19614c2127ce3d57))

- **release**: Run semantic-release through uv
  ([#199](https://github.com/dataiku/dku-headless/pull/199),
  [`368e488`](https://github.com/dataiku/dku-headless/commit/368e48873747016b65a8469a2708fafccc7905dc))

- **release**: Update release PR workflow and add branch matching for semantic release
  ([#238](https://github.com/dataiku/dku-headless/pull/238),
  [`fefc5e5`](https://github.com/dataiku/dku-headless/commit/fefc5e52be125df13a1cf7949986083036717549))

- **release**: Use reviewable release PR flow
  ([#238](https://github.com/dataiku/dku-headless/pull/238),
  [`fefc5e5`](https://github.com/dataiku/dku-headless/commit/fefc5e52be125df13a1cf7949986083036717549))

- **release**: Use stdlib python for PSR build_command instead of uv
  ([#199](https://github.com/dataiku/dku-headless/pull/199),
  [`368e488`](https://github.com/dataiku/dku-headless/commit/368e48873747016b65a8469a2708fafccc7905dc))

- **safety**: Ignore DKU_DANGEROUS in hosted MCP shells
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **security**: Redact api-key secrets, harden MCP file perms, narrow exceptions
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

### Documentation

- Add OSS community health files and contributor guides
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- Install from git, add lightweight community files
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- Make the README sandbox and safety claims transport-honest
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- Restore generic MCP client install path ([#168](https://github.com/dataiku/dku-headless/pull/168),
  [`b7edeff`](https://github.com/dataiku/dku-headless/commit/b7edeffdae6a7032bf0296991c223f4a6ab8888e))

- **mcp**: Make hosted-guard and session-lock comments honest
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **migration**: Close the "document deviations" loophole on the output-column contract
  ([#208](https://github.com/dataiku/dku-headless/pull/208),
  [`404826e`](https://github.com/dataiku/dku-headless/commit/404826e6bca0b0d347c991a9fa122be7b2b9de58))

- **migration**: Distinguish key vs measure typing in Alteryx skill
  ([#235](https://github.com/dataiku/dku-headless/pull/235),
  [`f917d1e`](https://github.com/dataiku/dku-headless/commit/f917d1ed699c4b4d7462c743d99c73ab965d36fa))

- **migration**: Enforce output-column-set fidelity for Alteryx terminal schema
  ([#208](https://github.com/dataiku/dku-headless/pull/208),
  [`404826e`](https://github.com/dataiku/dku-headless/commit/404826e6bca0b0d347c991a9fa122be7b2b9de58))

- **migration**: Rebuild the Alteryx app interface, not just the flow
  ([#209](https://github.com/dataiku/dku-headless/pull/209),
  [`ee4e6aa`](https://github.com/dataiku/dku-headless/commit/ee4e6aa5e142ec9164c90efbf5bb8c66d979d8ed))

- **migration**: Repurpose the default flow zone instead of stranding an empty one
  ([#207](https://github.com/dataiku/dku-headless/pull/207),
  [`5eb7d85`](https://github.com/dataiku/dku-headless/commit/5eb7d859b8aa542e63bd5ed79956365b1a1f35c2))

- **migration**: Require output verification — 1:1 parity, or schema-shape on synthetic data
  ([#206](https://github.com/dataiku/dku-headless/pull/206),
  [`58d52b6`](https://github.com/dataiku/dku-headless/commit/58d52b6ab3aad2953199627d6c91ffa2c78a3f1c))

- **skills**: Drop redundant --auto-update-schema from build commands
  ([#198](https://github.com/dataiku/dku-headless/pull/198),
  [`69ecbe2`](https://github.com/dataiku/dku-headless/commit/69ecbe2ef005711b68dd9512f22b89507591b4f9))

- **skills**: Refresh skill corpus, scrub internal codenames, add link checker
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **skills**: Restore migration logic-migration doctrine and ingestion guide
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

### Features

- Open-source launch readiness (release pipeline, security hardening, docs)
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **build**: Default --auto-update-schema on, with opt-out + change report
  ([#198](https://github.com/dataiku/dku-headless/pull/198),
  [`69ecbe2`](https://github.com/dataiku/dku-headless/commit/69ecbe2ef005711b68dd9512f22b89507591b4f9))

- **dataset**: Add typed enums for dataset creation options
  ([#171](https://github.com/dataiku/dku-headless/pull/171),
  [`0740feb`](https://github.com/dataiku/dku-headless/commit/0740febbb3a3c699237a96ec78f9e16677ddfdf0))

- **safety**: Guard semantic-model remove verbs and harden guard internals
  ([#173](https://github.com/dataiku/dku-headless/pull/173),
  [`925964e`](https://github.com/dataiku/dku-headless/commit/925964e425d5f2a6176deb0ddb12d429e532cd2c))


## [Unreleased]

## [0.4.1] - 2026-06-22

### Changed

- **Rebrand to Dataiku Headless.** The product/distribution identity is now
  "Dataiku Headless" (distribution name `dku-headless`). The `dku` command,
  the `dku_cli` import package, and all entry points are unchanged — only the
  product and distribution identity moved.

### Fixed

- **Exit-code correctness.** `dku scenario`, `dku ml train`, and
  `dku flow check` now propagate failure as a non-zero exit code instead of
  reporting success while the underlying job/run failed. Agents and CI can now
  trust the exit status as a build signal.

### Added

- **`dku sql` destructive-statement safety guard.** Destructive SQL statements
  (e.g. `DROP`, `TRUNCATE`, DDL/DML that mutates or removes data) are now gated
  behind the standard safety tiers, matching the rest of the CLI.
- **CI security scanning.** Added `pip-audit` (dependency CVEs), `gitleaks`
  (secret scanning), and CodeQL (static analysis) to CI, plus a
  wheel-freshness gate that blocks merges when the bundled wheel is stale
  relative to source.
- **`dataikuapi` contract/fidelity test.** A contract test pins the
  `dataikuapi` methods the CLI relies on, catching upstream API drift before it
  reaches users.

[Unreleased]: https://github.com/dataiku/dku-headless/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/dataiku/dku-headless/releases/tag/v0.4.1
