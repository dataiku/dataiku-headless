# Benchmark Architecture

```text
benchmark/
  runner.py           orchestrator — setup, agent run, checks, cleanup
  compare.py          cross-run comparison tables (pass/fail matrix + profile stats)
  config.yaml         profiles (surface presets via anchors), timeouts, parallelism
  docker/
    Dockerfile        runtime-only bench-agents image (no MCP source)
    Dockerfile.mcp    bench-mcp sidecar image — the MCP server over HTTP
    build.sh          stage context + build both images
    entrypoint.sh     exec the agent CLI under tini
  agents/
    base.py           BaseAgent, DockerAgent, AgentResult
    claude.py         Claude Code adapter (prepare config → docker run → parse)
    codex.py          Codex adapter (prepare config → docker run → parse)
    system_prompts/   agnostic.md, dku.md, dku_skills.md, mcp.md, mcp_skills.md
  analyzer/
    assertions.py     assertion registry
    coherence.py      per-trace tool-surface coherence check
    scorer.py         OutcomeScorer — Score dataclass
    reporter.py       summary.json + traces/
  scenarios/
    schema.py         NewScenario, Check, Checks, load_new_scenarios
    data_prep/ ...    one dir per domain
  fixtures/
    world/
    migration/
    generate_world.py
```

## Runner lifecycle

1. **Preflight** — check DSS connectivity, image freshness, report baked SHAs
2. **Setup** — create DSS project, run scenario `setup` commands, verify `initial_checks` fail
3. **Agent run** — launch Docker container with profile-specific surface (skills, PATH, creds, MCP URL), capture stdout
4. **Checks** — run each scenario `checks` command, assert on output, compute pass/fail
5. **Scoring** — `score = checks_passed / total_checks`; strict pass requires `score == 1.0`
6. **Coherence** — scan agent trace for surface violations (raw `DSSClient` in MCP profile, `dku` in vanilla, etc.)
7. **Teardown** — delete DSS project (unless `--no-cleanup`)
8. **Report** — write `summary.json` and per-test trace JSON to `reports/<run_id>/`

## Container isolation

- Agent runs inside `bench-agents` Docker image (runtime only: agent CLIs, `dku`, `dataikuapi`).
- No repo, scenarios, skills, or `.env` baked into the image — only what the profile grants per run.
- MCP server runs in a separate `bench-mcp` sidecar container over streamable-HTTP.
- The sidecar receives DSS creds; MCP-profile agents get only the URL — no creds, no MCP source.

See [Sandbox & coherence](../README.md#sandbox--coherence) for the full trace-level enforcement model.
