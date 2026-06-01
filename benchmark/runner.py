#!/usr/bin/env python3
"""Benchmark runner — outcome-based scenarios only."""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(Path(__file__).parent / ".env", override=True)
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.agents.base import (  # noqa: E402
    AgentResult,
    BaseAgent,
    OutcomeCheckResult,
    OutcomeVerification,
    _to_container_url,
)
from benchmark.agents.claude import ClaudeCodeAgent  # noqa: E402
from benchmark.agents.codex import CodexAgent  # noqa: E402
from benchmark.analyzer import coherence  # noqa: E402
from benchmark.analyzer.assertions import ASSERTION_REGISTRY  # noqa: E402
from benchmark.analyzer.reporter import Reporter, TestResultRecord  # noqa: E402
from benchmark.analyzer.scorer import OutcomeScorer, Score  # noqa: E402
from benchmark.scenarios.schema import (  # noqa: E402
    Check,
    NewScenario,
    load_new_scenarios,
)


# Under the repo, not $TMPDIR: macOS /var/folders isn't reliably shared with Docker Desktop.
FIXTURE_BASE = PROJECT_ROOT / "benchmark" / ".bench_scratch" / "fixtures"

MCP_SIDECAR_PORT = 8000
MCP_SIDECAR_ALIAS = "bench-mcp"
MCP_SIDECAR_PATH = "/mcp"

_EMBEDDING_LLM: str = ""


def load_config(config_path: Path | None = None) -> dict:
    """Load benchmark configuration."""
    path = config_path or Path(__file__).parent / "config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def collect_image_provenance(config: dict) -> dict:
    """Tool versions + build SHAs from the sandbox image itself (the host's may differ)."""
    image = config["runner"].get("sandbox_image", "bench-agents:latest")
    env: dict = {}
    try:
        digest = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()
        env["image"] = image
        env["image_id"] = digest
        probe = (
            "echo dku=$(dku --version 2>&1 | grep -o 'dku-cli [0-9.]*' | head -1); "
            "echo codex=$(codex --version 2>&1 | tr -d '\\n'); "
            "echo claude=$(claude --version 2>&1 | tr -d '\\n'); "
            "echo build=$(cat /opt/bench/BUILD_INFO.json 2>/dev/null)"
        )
        out = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "bash", image, "-lc", probe],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
        for line in out.splitlines():
            key, _, val = line.partition("=")
            if key == "build" and val.strip():
                import json as _json

                env["build_info"] = _json.loads(val)
            elif key in ("dku", "codex", "claude"):
                env[key] = val.strip()
        mcp_image = config["runner"].get("mcp_sidecar_image", "bench-mcp:latest")
        mcp_id = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", mcp_image],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if mcp_id.returncode == 0:
            env["mcp_image"] = mcp_image
            env["mcp_image_id"] = mcp_id.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        env["error"] = f"provenance probe failed: {exc}"
    return env


def _git_short_sha(repo: Path) -> str | None:
    """Short HEAD SHA of a host checkout, or None if unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:  # noqa: BLE001
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def check_image_freshness(config: dict) -> None:
    """Warn non-fatally when the sandbox image is behind the host checkouts (it bakes dku + MCP)."""
    image = config["runner"].get("sandbox_image", "bench-agents:latest")
    try:
        out = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "cat",
                image,
                "/opt/bench/BUILD_INFO.json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  Freshness: skipped ({exc})")
        return
    if out.returncode != 0:
        print("  Freshness: skipped (image has no BUILD_INFO; rebuild with build.sh)")
        return
    import json as _json

    built = _json.loads(out.stdout)
    adk_path = Path(
        PROJECT_ROOT
        / os.path.expandvars(
            os.environ.get("AGENT_DEV_KIT_SRC")
            or os.environ.get("AGENT_DEV_KIT_PATH", "../dataiku-agent-dev-kit")
        )
    ).resolve()

    checks = [
        ("dku-cli", PROJECT_ROOT, built.get("dku_cli_sha")),
        ("agent-dev-kit", adk_path, built.get("agent_dev_kit_sha")),
    ]
    stale = []
    for name, repo, baked in checks:
        head = _git_short_sha(repo)
        if head and baked and baked != "unknown" and not head.startswith(baked):
            stale.append(f"{name}: image={baked} host={head}")
    if stale:
        print("  Freshness: WARNING — sandbox image is behind host checkouts:")
        for line in stale:
            print(f"    - {line}")
        print(
            "    The baked dku CLI / MCP server are stale. Rebuild: "
            "benchmark/docker/build.sh  (add --pull to fetch origin first)"
        )
    else:
        print("  Freshness: image matches host checkouts")


def start_mcp_sidecar(config: dict, run_id: str, agents: list) -> dict | None:
    """Start the dataiku MCP sidecar on a per-run network; exits on failure, None when no MCP profile."""
    mcp_agents = [a for a in agents if getattr(a, "has_mcp", False)]
    if not mcp_agents:
        return None

    # All MCP profiles in a run share one sidecar, so they must agree on tool_exposure.
    exposures = {a.agent_config.get("tool_exposure", "full") for a in mcp_agents}
    if len(exposures) > 1:
        print(
            "  ERROR: MCP profiles disagree on tool_exposure. "
            f"Got {sorted(exposures)}. Use separate runs for different modes."
        )
        sys.exit(1)
    tool_exposure = next(iter(exposures))

    image = config["runner"].get("mcp_sidecar_image", "bench-mcp:latest")
    if (
        subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, text=True
        ).returncode
        != 0
    ):
        print(
            f"  ERROR: MCP sidecar image {image!r} not found. "
            "Build it: benchmark/docker/build.sh"
        )
        sys.exit(1)

    network = f"bench_net_{run_id}"
    container = f"bench_mcp_{run_id}"
    container_url = _to_container_url(os.environ.get("DKU_URL", ""))
    key = os.environ.get("DKU_API_KEY", "")

    subprocess.run(
        ["docker", "network", "create", network],
        capture_output=True,
        text=True,
        timeout=30,
    )
    run_cmd = [
        "docker", "run", "-d", "--rm",
        "--name", container,
        "--network", network,
        "--network-alias", MCP_SIDECAR_ALIAS,
        "--add-host", "host.docker.internal:host-gateway",
        "-e", f"DATAIKU_URL={container_url}",
        "-e", f"DATAIKU_API_KEY={key}",
        "-e", f"DATAIKU_MCP_TOOL_EXPOSURE={tool_exposure}",
        image,
    ]  # fmt: skip
    res = subprocess.run(run_cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        subprocess.run(
            ["docker", "network", "rm", network], capture_output=True, text=True
        )
        print(f"  ERROR: failed to start MCP sidecar: {res.stderr.strip()[:300]}")
        sys.exit(1)

    sidecar = {"network": network, "container": container, "image": image}
    config["runner"]["mcp_sidecar"] = sidecar

    print("  MCP sidecar: waiting for healthy...")
    deadline = time.monotonic() + 60
    healthy = False
    while time.monotonic() < deadline:
        h = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", container],
            capture_output=True,
            text=True,
        )
        if h.returncode != 0:
            break  # container exited
        if h.stdout.strip() == "healthy":
            healthy = True
            break
        time.sleep(2)

    if not healthy:
        logs = subprocess.run(
            ["docker", "logs", "--tail", "30", container],
            capture_output=True,
            text=True,
        )
        stop_mcp_sidecar(config)
        print(
            "  ERROR: MCP sidecar did not become healthy.\n"
            f"{(logs.stderr + logs.stdout).strip()[-600:]}"
        )
        sys.exit(1)

    url = f"http://{MCP_SIDECAR_ALIAS}:{MCP_SIDECAR_PORT}{MCP_SIDECAR_PATH}"
    sidecar["url"] = url
    print(f"  MCP sidecar: healthy at {url} (network {network})")
    return sidecar


def stop_mcp_sidecar(config: dict) -> None:
    """Stop the MCP sidecar and remove its network. Safe to call when none ran."""
    sidecar = (config.get("runner") or {}).get("mcp_sidecar")
    if not sidecar:
        return
    if sidecar.get("container"):
        subprocess.run(
            ["docker", "stop", sidecar["container"]],
            capture_output=True,
            text=True,
            timeout=30,
        )
    if sidecar.get("network"):
        subprocess.run(
            ["docker", "network", "rm", sidecar["network"]],
            capture_output=True,
            text=True,
            timeout=30,
        )


def _agent_configs(config: dict) -> dict:
    return config.get("profiles") or {}


def _resolve_agent_names(args: argparse.Namespace, config: dict) -> list[str]:
    if getattr(args, "profile", None):
        return [p.strip() for p in args.profile.split(",") if p.strip()]
    return config.get("runner", {}).get("profiles", [])


def _apply_model_override(
    agent_names: list[str], config: dict, model: str | None
) -> None:
    if not model:
        return
    configs = _agent_configs(config)
    for name in agent_names:
        configs[name]["model"] = model


def _agent_class(config: dict, name: str):
    vendor = (_agent_configs(config)[name].get("vendor") or "").lower()
    if vendor == "codex":
        return CodexAgent
    if vendor == "claude":
        return ClaudeCodeAgent
    raise ValueError(f"profile {name!r} must set vendor: codex|claude")


def _build_agents(agent_names: list[str], config: dict) -> list:
    return [_agent_class(config, name)(config, name) for name in agent_names]


def preflight_check(agent_names: list[str], config: dict) -> None:
    """Verify DSS connectivity and required env vars before running benchmarks."""
    print("  Preflight: checking DSS connectivity...")
    try:
        result = subprocess.run(
            ["dku", "whoami"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        print(
            "  ERROR: dku CLI not found. Install with: uv tool install --from /path/to/dku-cli dku-cli"
        )
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("  ERROR: dku whoami timed out. Check DSS connectivity.")
        sys.exit(1)

    if result.returncode != 0:
        print(f"  ERROR: dku whoami failed: {result.stderr}")
        sys.exit(1)
    print(f"  Connected: {result.stdout.strip()[:100]}")
    check_image_freshness(config)


def create_project(project_key: str, name: str) -> bool:
    """Create a DSS project for a test."""
    result = subprocess.run(
        ["dku", "project", "create", project_key, "--name", name],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        return True
    already_exists = "already exists" in (f"{result.stdout}\n{result.stderr}".lower())
    if already_exists:
        return True
    print(f"  Warning: failed to create project {project_key}: {result.stderr}")
    return False


def cleanup_project(project_key: str, drop_data: bool = False) -> bool:
    """Delete a DSS project after a run."""
    cmd = [
        "dku",
        "project",
        "delete",
        project_key,
        "--yes",
        "--confirm-name",
        project_key,
    ]
    if drop_data:
        cmd.append("--drop-data")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode == 0


def build_project_key(run_id: str, scenario_id: str, prefix: str = "BENCH") -> str:
    """Build a bounded DSS project key. Nonce prevents collisions across profiles."""
    suffix = run_id[-6:].upper()
    compact_id = "".join(ch for ch in scenario_id.upper() if ch.isalnum())
    nonce = secrets.token_hex(2)
    key = f"{prefix}_{suffix}_{nonce}_{compact_id}"
    return key[:25]


def get_fixture_target(test_id: str, agent_name: str = "shared") -> Path:
    """Return a per-test fixture directory to avoid race conditions."""
    return FIXTURE_BASE / f"{test_id}_{agent_name}"


def inject_new_fixtures(scenario: NewScenario, config: dict, agent_name: str) -> Path:
    """Copy new-world fixtures to a per-test temp dir."""
    target = get_fixture_target(scenario.id, agent_name)
    fixture_base = Path(config["runner"].get("fixture_dir", "benchmark/fixtures"))
    target.mkdir(parents=True, exist_ok=True)
    for ref in scenario.fixtures:
        src = fixture_base / f"{ref}.csv"
        if src.is_file():
            shutil.copy2(src, target / src.name)
            continue
        src_dir = fixture_base / ref
        if src_dir.is_dir():
            for file_path in src_dir.iterdir():
                if file_path.is_file():
                    shutil.copy2(file_path, target / file_path.name)
            continue
        print(f"  Warning: fixture not found: {ref}")
    return target


def cleanup_fixtures() -> None:
    """Remove all temporary fixture directories."""
    shutil.rmtree(FIXTURE_BASE, ignore_errors=True)


def resolve_new_prompt(scenario: NewScenario, fixture_target: Path) -> str:
    """Resolve placeholders in a new scenario prompt."""
    prompt = scenario.prompt.replace("{project}", scenario.project_key or "")
    prompt = prompt.replace("{fixture_dir}", str(fixture_target))
    return prompt


def _run_command(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _format_command(
    command: str, project_key: str | None = None, fixture_dir: Path | None = None
) -> str:
    resolved = command
    if project_key:
        resolved = resolved.replace("{project}", project_key)
    if fixture_dir:
        resolved = resolved.replace("{fixture_dir}", str(fixture_dir))
    if _EMBEDDING_LLM:
        resolved = resolved.replace("{embedding_llm}", _EMBEDDING_LLM)
    return resolved


def _evaluate_check(
    check: Check,
    project_key: str,
    fixture_dir: Path | None = None,
    timeout: int = 60,
    context: dict | None = None,
) -> OutcomeCheckResult:
    cmd = _format_command(check.run, project_key, fixture_dir)
    result = _run_command(cmd, timeout=timeout)
    assertion = ASSERTION_REGISTRY[check.assert_]
    passed, message = assertion(result.stdout, result.returncode, check, context or {})
    return OutcomeCheckResult(
        check_name=check.assert_,
        command=cmd,
        passed=passed,
        message=message or result.stderr.strip()[:300],
        output=result.stdout[:500],
        exit_code=result.returncode,
    )


def run_setup(scenario: NewScenario, fixture_dir: Path) -> None:
    """Execute pre-agent setup commands."""
    for command in scenario.setup:
        resolved = _format_command(command, scenario.project_key, fixture_dir)
        result = _run_command(resolved)
        if result.returncode != 0:
            raise RuntimeError(
                f"Setup failed: {resolved}\n{(result.stderr or result.stdout).strip()[:400]}"
            )


def run_initial_checks(scenario: NewScenario, fixture_dir: Path) -> None:
    """Confirm the initial state is still broken before the agent runs."""
    for check in scenario.initial_checks:
        result = _evaluate_check(check, scenario.project_key or "", fixture_dir)
        if not result.passed:
            raise RuntimeError(
                f"Initial check failed: {result.command} ({result.check_name}) :: {result.message}"
            )


def _needs_dss_client(scenario: NewScenario) -> bool:
    """Check if any checks or specs require a DSS client."""
    if scenario.expected_outputs or scenario.expected_flow:
        return True
    dss_assertions = {
        "flow_shape",
        "output_schema",
        "output_rows",
    }
    return any(c.assert_ in dss_assertions for c in scenario.checks)


def _build_check_context(scenario: NewScenario) -> dict:
    """Build a context dict for checks, including DSS client when needed."""
    context: dict = {}
    if scenario.expected_outputs:
        context["expected_outputs"] = scenario.expected_outputs
    if scenario.expected_flow:
        context["expected_flow"] = scenario.expected_flow
    if scenario.project_key:
        context["project_key"] = scenario.project_key
    if _needs_dss_client(scenario):
        try:
            from dataikuapi import DSSClient

            import os

            url = os.environ.get("DKU_URL", "")
            key = os.environ.get("DKU_API_KEY", "")
            if url and key:
                context["client"] = DSSClient(url, key)
        except Exception as e:
            print(f"Warning: failed to create DSS client: {e}", file=sys.stderr)
    return context


def run_outcome_checks(
    scenario: NewScenario,
    fixture_dir: Path | None = None,
    extra_context: dict | None = None,
) -> OutcomeVerification:
    """Run all outcome checks for a new scenario."""
    context = _build_check_context(scenario)
    if extra_context:
        context.update(extra_context)

    results = [
        _evaluate_check(check, scenario.project_key or "", fixture_dir, context=context)
        for check in scenario.checks
    ]
    return OutcomeVerification(results=results)


def extract_solution_commands(solution_file: Path) -> list[str]:
    """Extract commands from the first fenced bash block in solution.md."""
    content = solution_file.read_text()
    in_block = False
    commands: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") and not in_block:
            lang = stripped[3:].strip()
            in_block = lang in {"bash", "sh", ""}
            continue
        if stripped.startswith("```") and in_block:
            break
        if in_block and stripped and not stripped.startswith("#"):
            commands.append(stripped)
    return commands


def validate_scenario(
    scenario: NewScenario,
    config: dict,
    no_cleanup: bool = False,
    drop_data: bool = False,
) -> tuple[bool, str]:
    """Run setup + solution + checks to prove a scenario is solvable."""
    scenario = scenario.model_copy(
        update={
            "project_key": build_project_key(
                datetime.now().strftime("%Y%m%d_%H%M%S"),
                scenario.id,
                prefix=config.get("dss", {}).get("project_prefix", "BENCH"),
            )
        }
    )
    fixture_dir = inject_new_fixtures(scenario, config, "validate")
    if not create_project(scenario.project_key, f"Benchmark {scenario.id} validation"):
        return False, "project creation failed"

    try:
        run_setup(scenario, fixture_dir)
        run_initial_checks(scenario, fixture_dir)
        if not scenario.solution_file:
            return False, "missing solution.md"
        commands = extract_solution_commands(scenario.solution_file)
        if not commands:
            return False, "no commands found in solution.md"
        for command in commands:
            resolved = _format_command(command, scenario.project_key, fixture_dir)
            result = _run_command(resolved, timeout=120)
            if result.returncode != 0:
                return (
                    False,
                    f"solution failed: {resolved} :: {(result.stderr or result.stdout).strip()[:240]}",
                )
        verification = run_outcome_checks(scenario, fixture_dir)
        score = OutcomeScorer().score(scenario, verification)
        if not score.passed:
            return False, "; ".join(score.details.values()) or "outcome checks failed"
        return True, "validated"
    finally:
        if not no_cleanup:
            cleanup_project(scenario.project_key, drop_data=drop_data)


def _resolve_tiered(cfg_value, difficulty, scenario_override, fallback):
    """Resolve a runner setting: per-scenario override > difficulty tier > default.

    `cfg_value` may be a scalar (applies to all difficulties) or a mapping with
    `default` plus optional easy/medium/hard keys.
    """
    if scenario_override is not None:
        return scenario_override
    if isinstance(cfg_value, dict):
        return cfg_value.get(difficulty, cfg_value.get("default", fallback))
    if cfg_value is not None:
        return cfg_value
    return fallback


def run_single_new_test(
    agent: BaseAgent,
    scenario: NewScenario,
    config: dict,
    run_id: str,
    no_cleanup: bool = False,
    drop_data: bool = False,
) -> TestResultRecord:
    """Run a single outcome-based scenario with one agent."""
    scenario = scenario.model_copy(
        update={
            "project_key": build_project_key(
                run_id,
                scenario.id,
                prefix=config.get("dss", {}).get("project_prefix", "BENCH"),
            )
        }
    )
    fixture_target = inject_new_fixtures(scenario, config, agent.name)

    if not create_project(scenario.project_key, f"Benchmark {scenario.id}"):
        raise RuntimeError(f"Failed to create project {scenario.project_key}")

    try:
        run_setup(scenario, fixture_target)
        run_initial_checks(scenario, fixture_target)

        prompt = resolve_new_prompt(scenario, fixture_target)
        runner_cfg = config["runner"]
        timeout = _resolve_tiered(
            runner_cfg.get("timeout"), scenario.difficulty, scenario.timeout, 300
        )
        max_turns = _resolve_tiered(
            runner_cfg.get("max_turns"), scenario.difficulty, scenario.max_turns, None
        )
        start = time.monotonic()
        request_context = {
            "run_id": run_id,
            "scenario_id": scenario.id,
            "project_key": scenario.project_key,
            "sources": [Path(ref).name for ref in scenario.fixtures],
        }
        agent_result = agent.run(
            prompt,
            str(fixture_target),
            timeout=timeout,
            request_context=request_context,
            max_turns=max_turns,
        )
        wall_ms = int((time.monotonic() - start) * 1000)
        if not agent_result.duration_ms:
            agent_result.duration_ms = wall_ms

        verification = run_outcome_checks(
            scenario,
            fixture_target,
            extra_context={"tool_trace": agent_result.tool_calls},
        )
        score = OutcomeScorer().score(scenario, verification)

        return TestResultRecord(
            test_id=scenario.id,
            category=scenario.domain,
            prompt=prompt,
            agent=agent.name,
            score=score,
            agent_result=agent_result,
            difficulty=scenario.difficulty,
            gap_type=scenario.expected_gap,
        )
    finally:
        if not no_cleanup and config["runner"].get("cleanup", True):
            cleanup_project(scenario.project_key, drop_data=drop_data)


def _filter_new_scenarios(
    scenarios: list[NewScenario], args: argparse.Namespace
) -> list[NewScenario]:
    filtered = scenarios
    scenario_id = getattr(args, "scenario", None) or getattr(args, "test", None)
    if scenario_id:
        ids = {s.strip() for s in scenario_id.split(",")}
        filtered = [s for s in filtered if s.id in ids]
    if args.domain:
        domains = {d.strip() for d in args.domain.split(",")}
        filtered = [s for s in filtered if s.domain in domains]
    if args.difficulty:
        levels = {lv.strip() for lv in args.difficulty.split(",")}
        filtered = [s for s in filtered if s.difficulty in levels]
    return filtered


def _dry_run_new(scenarios: list[NewScenario], agents: list[BaseAgent]) -> None:
    print("\n  Dry run — new scenarios that would execute:")
    for scenario in scenarios:
        fixtures = ",".join(scenario.fixtures) if scenario.fixtures else "-"
        for agent in agents:
            print(
                f"    [{agent.name:6s}] {scenario.id:25s} domain={scenario.domain:12s} difficulty={scenario.difficulty:6s} fixtures={fixtures}"
            )


def run_validate_mode(
    scenarios: list[NewScenario],
    config: dict,
    no_cleanup: bool = False,
    drop_data: bool = False,
) -> int:
    print(f"  Validating {len(scenarios)} scenario(s) against DSS...\n")
    failed = 0
    for scenario in scenarios:
        ok, message = validate_scenario(
            scenario,
            config,
            no_cleanup=no_cleanup,
            drop_data=drop_data,
        )
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {scenario.id:25s} {message}")
        if not ok:
            failed += 1
    return 1 if failed else 0


def _list_command(config: dict) -> None:
    scenario_dir = Path(__file__).parent / "scenarios"
    scenarios = load_new_scenarios(scenario_dir)

    print("\n  Profiles:")
    for name, pcfg in (config.get("profiles") or {}).items():
        default = " (default)" if name in config["runner"].get("profiles", []) else ""
        print(f"    {name:20s}  model={pcfg.get('model', '?')}{default}")

    print(f"\n  Scenarios ({len(scenarios)}):")
    by_domain: dict[str, list] = {}
    for s in scenarios:
        by_domain.setdefault(s.domain, []).append(s)
    for domain, ss in sorted(by_domain.items()):
        print(f"    {domain}/")
        for s in sorted(ss, key=lambda x: x.id):
            print(f"      {s.id:35s}  {s.difficulty:6s}  gap={s.expected_gap}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="dku-cli Benchmark Runner")
    parser.add_argument(
        "--profile",
        type=str,
        help="Profile(s) to run, comma-separated (e.g. claude_vanilla,codex_dku_skills). Default: config runner.profiles",
    )
    parser.add_argument(
        "--scenario", type=str, help="Run scenario(s) by ID (comma-separated)"
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Override model for selected profile(s) (e.g. claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--parallel", type=int, default=None, help="Max parallel workers"
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=None,
        help="Run each scenario N times per profile for statistical stability (default: config runner.repeat or 1)",
    )
    parser.add_argument("--config", type=str, default=None, help="Config file path")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available profiles and scenarios then exit",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would run without executing"
    )
    parser.add_argument(
        "--skip-preflight", action="store_true", help="Skip DSS connectivity check"
    )
    parser.add_argument("--domain", type=str, help="Filter by domain (comma-separated)")
    parser.add_argument(
        "--difficulty", type=str, help="Filter by difficulty (easy,medium,hard)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run solution.md against DSS before benchmarking",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Keep DSS projects after each run for debugging",
    )
    parser.add_argument(
        "--drop-data",
        action="store_true",
        help="Drop managed backing data when cleanup deletes benchmark projects",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Stream agent commands to terminal as they execute (best with --parallel 1)",
    )
    args = parser.parse_args()

    config = load_config(Path(args.config) if args.config else None)

    global _EMBEDDING_LLM
    _EMBEDDING_LLM = config.get("dss", {}).get("embedding_llm", "")

    if args.list:
        _list_command(config)
        return

    run_id = f"bench_{datetime.now():%Y%m%d_%H%M%S}"

    print(f"\n  Benchmark: {run_id}")
    print(f"  {'=' * 50}")

    agent_names = _resolve_agent_names(args, config)
    _apply_model_override(agent_names, config, args.model)
    agents = _build_agents(agent_names, config)
    if args.verbose:
        for agent in agents:
            agent.verbose = True
    model_suffix = f" [{args.model}]" if args.model else ""
    print(f"  Profiles: {', '.join(a.name for a in agents)}{model_suffix}")

    scenario_dir = Path(__file__).parent / "scenarios"
    scenarios = _filter_new_scenarios(load_new_scenarios(scenario_dir), args)
    if not scenarios:
        print("  ERROR: no scenarios matched the filters")
        sys.exit(1)
    print("  Mode: outcome")
    print(f"  Scenarios: {len(scenarios)}")
    if args.domain:
        print(f"  Domain filter: {args.domain}")
    if args.difficulty:
        print(f"  Difficulty filter: {args.difficulty}")

    repeat = max(1, args.repeat or config["runner"].get("repeat", 1))
    total_runs = len(scenarios) * len(agents) * repeat
    repeat_note = f" x {repeat} repeats" if repeat > 1 else ""
    print(
        f"  Total runs: {total_runs} ({len(scenarios)} tests x {len(agents)} agents{repeat_note})"
    )

    if args.dry_run:
        _dry_run_new(scenarios, agents)
        return

    if not args.skip_preflight:
        preflight_check(agent_names, config)

    if args.validate:
        sys.exit(
            run_validate_mode(
                scenarios,
                config,
                no_cleanup=args.no_cleanup,
                drop_data=args.drop_data,
            )
        )

    parallel = args.parallel or config["runner"].get("parallel", 4)
    results: list[TestResultRecord] = []
    completed = 0

    start_mcp_sidecar(config, run_id, agents)
    try:
        print(f"\n  Running {total_runs} tests (parallel={parallel})...\n")

        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {}
            for agent in agents:
                for scenario in scenarios:
                    for _ in range(repeat):
                        future = pool.submit(
                            run_single_new_test,
                            agent,
                            scenario,
                            config,
                            run_id,
                            args.no_cleanup,
                            args.drop_data,
                        )
                        futures[future] = (agent.name, scenario)

            for future in as_completed(futures):
                agent_name, scenario = futures[future]
                test_id = scenario.id
                try:
                    record = future.result()
                    results.append(record)
                    completed += 1
                    if record.score.passed:
                        status = "PASS"
                    elif record.agent_result.timed_out:
                        status = "TIMEOUT"
                    else:
                        status = "FAIL"
                    issues = coherence.check(
                        record.agent,
                        record.agent_result.bash_commands,
                        record.agent_result.mcp_calls,
                    )
                    coh = (
                        "coherent" if not issues else f"INCOHERENT: {'; '.join(issues)}"
                    )
                    print(
                        f"  [{completed:3d}/{total_runs}] {status:7s} {agent_name:6s} {test_id:25s} "
                        f"score={record.score.score:.0%} {record.agent_result.duration_ms}ms "
                        f"${record.agent_result.cost_usd:.3f} [{coh}]"
                    )
                except Exception as exc:  # noqa: BLE001
                    completed += 1
                    # Record the failure (tagged `errored`) instead of dropping it
                    # and silently shrinking the denominator.
                    results.append(
                        TestResultRecord(
                            test_id=test_id,
                            category=scenario.domain,
                            prompt="",
                            agent=agent_name,
                            score=Score(
                                score=0.0,
                                gap_type=scenario.expected_gap,
                                details={"harness_error": str(exc)[:300]},
                            ),
                            agent_result=AgentResult(
                                agent=agent_name,
                                errored=True,
                                errors=[str(exc)[:500]],
                            ),
                            difficulty=scenario.difficulty,
                            gap_type=scenario.expected_gap,
                        )
                    )
                    print(
                        f"  [{completed:3d}/{total_runs}] {'ERR':7s} {agent_name:6s} {test_id:25s} {exc}"
                    )
    finally:
        stop_mcp_sidecar(config)

    print("\n  Generating reports...")
    reporter = Reporter(
        run_id, config=config, environment=collect_image_provenance(config)
    )
    reporter.generate(results)

    cleanup_fixtures()

    print(f"\n  Done. Reports at: benchmark/reports/{run_id}/")


if __name__ == "__main__":
    main()
