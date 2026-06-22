# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.1] - 2026-06-22

### Changed

- **Rebrand to Dataiku Headless.** The product/distribution identity is now
  "Dataiku Headless" (distribution name `dataiku-headless`). The `dku` command,
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
