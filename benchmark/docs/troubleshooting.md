# Benchmark Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `dku whoami` fails | CLI not installed or wrong DSS URL | `uv tool install --from . dku-cli` then check `DKU_URL` in `.env` |
| `docker: command not found` | Docker not installed or not on PATH | Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| `agent-dev-kit not found` on build | `AGENT_DEV_KIT_SRC` not set and no sibling checkout | `export AGENT_DEV_KIT_SRC=/path/to/dataiku-agent-dev-kit` |
| `docker build` fails with network errors | Docker Builder can't reach npm/PyPI | Check Docker network settings; try `docker pull python:3.12-slim-bookworm` first |
| All runs fail with `DSSClient` errors | DSS URL/API key wrong, or instance unreachable | `dku whoami` from the host; check `DKU_URL` resolves inside Docker (`host.docker.internal` vs `localhost`) |
| `INCOHERENT: vanilla used the dku CLI` | `strip_dku` config not applied | Verify `vanilla` profile has `strip_dku: true` in `config.yaml` |
| `Setup failed: ...` in a specific scenario | Scenario `setup` commands don't match current DSS version or CLI | Run `--validate --scenario <id>` to reproduce; check the `solution.md` commands work manually |
| Docker container exits immediately with no output | Agent CLI not installed or entrypoint mismatch | `docker run --rm -it bench-agents:latest claude --version` to verify the image has the CLI |
| `no scenario matched the filters` | Misspelled scenario ID, domain, or difficulty | Run `--list` to see available values |
| Scenario passes on `--validate` but fails in agent run | Agent uses a different approach that doesn't satisfy checks | Inspect the trace JSON: `benchmark/reports/<run_id>/traces/<test_id>_<agent>.json` |

## Coherence issues

| Tag | Meaning | Action |
|---|---|---|
| `coherent` | Agent stayed within its granted tool surface | No action needed |
| `INCOHERENT: vanilla used the dku CLI` | Vanilla profile called `dku` commands | Check `strip_dku: true` in config; verify `dku` is off `PATH` in stripped profiles |
| `INCOHERENT: mcp used raw DSSClient` | MCP profile called `DSSClient()` directly | Verify `DKU_URL`/`DKU_API_KEY` are NOT in the agent container env |
| `INCOHERENT: dku_skills read solution.md` | Agent read the solution file | Check bind-mount exclusions in the runner |
| `INCOHERENT: … read its own agent config under /cfg` | Agent read `/cfg/config.toml`, `auth.json`, or `mcp.json` | Defense-in-depth only — post-sidecar `/cfg` holds just a URL, no creds |

## Freshness warnings

The runner prints a **Freshness** line at preflight and warns when the running image was built from older commits than your host checkouts. Rebuild with:

```bash
benchmark/docker/build.sh --pull            # latest dku + MCP
benchmark/docker/build.sh --pull --no-cache # also refresh the agent CLIs
```
