# Benchmark CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--profile` | `runner.profiles` in config | Comma-separated profile names (e.g. `claude_vanilla,claude_dku_skills`) |
| `--model` | profile config | Override model for selected profiles (e.g. `claude-sonnet-4-6`) |
| `--scenario` | all | Run a single scenario by ID |
| `--domain` | all | Filter by domain, comma-separated |
| `--difficulty` | all | Filter by difficulty (`easy`, `medium`, `hard`) |
| `--list` | — | Print profiles and scenarios, then exit |
| `--dry-run` | — | Show what would run without executing |
| `--validate` | — | Run `solution.md` commands against DSS, verify checks pass |
| `--no-cleanup` | — | Keep DSS projects after each run |
| `--drop-data` | — | When cleanup runs, also drop managed backing data for benchmark projects |
| `--repeat` | `runner.repeat` in config (`1`) | Run each scenario N times per profile; reports min/max/mean/stddev of duration & cost plus pass rate (k/N) |
| `--parallel` | config | Max parallel workers |
| `--config` | `benchmark/config.yaml` | Path to config file |
| `--skip-preflight` | — | Skip DSS connectivity check |

## Profile config keys

Defined in `config.yaml`. See [Profiles](README.md#profiles) for available presets.

| Key | Description |
|-----|-------------|
| `vendor` | `codex` or `claude` — selects the adapter |
| `model` | Model ID; can be overridden with `--model` |
| `skills` | Skill names to expose (copied into the agent's skill dir per run) |
| `skills_root` | Skill source dir (default: `dataiku-devkit/skills`) |
| `auto_discover_skills` | Expose every skill under `skills_root` |
| `mcp_servers` | MCP servers to wire up; presence implies an MCP-only profile |
| `system_prompt` | Path relative to repo root (Codex writes it as `AGENTS.md` in `/work`) |
| `effort` | Effort level passed to the agent (`low`, `medium`, `high`) |
| `max_turns` | Max agent turns |
| `strip_dku` | Drop the `dku` CLI from `PATH` (implied for MCP profiles) |
