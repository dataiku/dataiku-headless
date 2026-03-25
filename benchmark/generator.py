#!/usr/bin/env python3
"""Auto-generate Tier 1 test scenarios from the CLAUDE.md command table.

Reads the 'Command -> dataikuapi Mapping' table and generates a YAML file
with one test per CLI command.

Usage:
    python -m benchmark.generator
    python -m benchmark.generator --output benchmark/scenarios/tier1_generated.yaml
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent

# Templates for generating natural language prompts from command patterns
VERB_TEMPLATES = {
    "list": [
        "List all {noun}s in project {{project}}.",
        "Show me the {noun}s available in project {{project}}.",
    ],
    "get": [
        "Get the details of {noun} '{arg}' in project {{project}}.",
        "Show me {noun} '{arg}' in project {{project}}.",
    ],
    "create": [
        "Create a new {noun} called '{arg}' in project {{project}}.",
    ],
    "delete": [
        "Delete {noun} '{arg}' from project {{project}}.",
    ],
    "run": [
        "Run {noun} '{arg}' in project {{project}}.",
        "Execute {noun} '{arg}' in project {{project}}.",
    ],
    "status": [
        "Show the status of {noun} '{arg}' in project {{project}}.",
        "What's the current status of {noun} '{arg}'?",
    ],
    "export": [
        "Export {noun} '{arg}' from project {{project}}.",
    ],
    "search": [
        "Search {noun} '{arg}' for relevant content in project {{project}}.",
    ],
    "build": [
        "Build {noun} '{arg}' in project {{project}}.",
    ],
    "schema": [
        "Show the schema of {noun} '{arg}' in project {{project}}.",
    ],
    "head": [
        "Show the first few rows of {noun} '{arg}' in project {{project}}.",
    ],
    "graph": [
        "Show the {noun} graph for project {{project}}.",
    ],
    "zones": [
        "List the {noun} zones in project {{project}}.",
    ],
    "variables": [
        "Show the variables for project {{project}}.",
    ],
    "permissions": [
        "Show the permissions for project {{project}}.",
    ],
    "log": [
        "Show the log for {noun} '{arg}' in project {{project}}.",
    ],
    "abort": [
        "Abort {noun} '{arg}' in project {{project}}.",
    ],
    "query": [
        "Run a SQL query on the DSS instance.",
    ],
}

# Nouns that don't need --project
GLOBAL_NOUNS = {"plugin", "code-env", "connection", "user", "config", "auth"}

# Default arg placeholder per noun
DEFAULT_ARGS = {
    "project": "MYPROJ",
    "dataset": "my_dataset",
    "recipe": "compute_features",
    "scenario": "build_all",
    "job": "job123",
    "plugin": "my-plugin",
    "code-env": "py311",
    "connection": "pg_main",
    "model": "model1",
    "folder": "data_folder",
    "llm": "openai:gpt-4",
    "webapp": "dashboard",
    "macro": "my_macro",
    "user": "analyst1",
    "flow": "",
    "library": "python/utils.py",
    "agent": "agent1",
    "agent-tool": "my_tool",
    "knowledge": "kb1",
    "bundle": "v1",
    "api-service": "myservice",
    "wiki": "Home",
    "sql": "SELECT 1",
}


def parse_command_table(claude_md_path: Path) -> list[dict]:
    """Parse the command -> dataikuapi mapping table from CLAUDE.md."""
    content = claude_md_path.read_text()

    # Find the mapping table section
    pattern = r'\| `(dku [^`]+)` \|'
    matches = re.findall(pattern, content)

    commands = []
    for match in matches:
        # Parse: "dku noun verb [ARGS]"
        parts = match.strip().split()
        if len(parts) < 3:
            continue

        noun = parts[1]
        verb = parts[2]
        args = " ".join(parts[3:]) if len(parts) > 3 else ""

        commands.append({
            "full_command": match.strip(),
            "noun": noun,
            "verb": verb,
            "args": args,
        })

    return commands


def generate_prompt(cmd: dict) -> str:
    """Generate a natural language prompt for a command."""
    noun = cmd["noun"]
    verb = cmd["verb"]
    arg = cmd["args"] or DEFAULT_ARGS.get(noun, "X")

    templates = VERB_TEMPLATES.get(verb, [f"Use the dku CLI to {verb} {noun}."])
    template = templates[0]

    prompt = template.format(
        noun=noun.replace("-", " "),
        arg=arg.replace("NAME", "my_item").replace("ID", "item1").replace("KEY", "MYPROJ"),
    )

    # Replace {project} placeholder for global commands
    if noun in GLOBAL_NOUNS:
        prompt = prompt.replace(" in project {project}", "").replace(" from project {project}", "")

    return prompt


def generate_scenario(cmd: dict, index: int) -> dict:
    """Generate a test scenario for a command."""
    noun = cmd["noun"]
    verb = cmd["verb"]
    needs_project = noun not in GLOBAL_NOUNS

    # Build expected command pattern
    cmd_pattern = f"dku {noun} {verb}"

    # Determine flags
    flags = []
    if needs_project:
        flags.append("-P {project}")

    scenario = {
        "id": f"t1_gen_{noun.replace('-', '_')}_{verb.replace('-', '_')}_{index:03d}",
        "tier": 1,
        "category": noun,
        "prompt": generate_prompt(cmd),
        "needs_project": needs_project,
        "expect": {
            "commands": [
                {"pattern": cmd_pattern, "required": True},
            ],
        },
        "rubric": {
            "command_correct": 1.0,
            "efficiency": 0.5,
        },
    }

    if flags:
        scenario["expect"]["commands"][0]["flags"] = flags

    return scenario


def generate_all(claude_md_path: Path) -> list[dict]:
    """Generate all tier 1 scenarios from CLAUDE.md."""
    commands = parse_command_table(claude_md_path)
    scenarios = []
    for i, cmd in enumerate(commands):
        scenario = generate_scenario(cmd, i)
        scenarios.append(scenario)
    return scenarios


def main():
    parser = argparse.ArgumentParser(description="Generate Tier 1 benchmark scenarios")
    parser.add_argument(
        "--output",
        default="benchmark/scenarios/tier1_generated.yaml",
        help="Output YAML file",
    )
    parser.add_argument(
        "--claude-md",
        default=str(PROJECT_ROOT / "CLAUDE.md"),
        help="Path to CLAUDE.md",
    )
    args = parser.parse_args()

    claude_md = Path(args.claude_md)
    if not claude_md.exists():
        print(f"ERROR: {claude_md} not found")
        return

    scenarios = generate_all(claude_md)
    output = {"tests": scenarios}

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {len(scenarios)} scenarios -> {out_path}")


if __name__ == "__main__":
    main()
