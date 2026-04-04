#!/usr/bin/env python3
"""Auto-generate benchmark scenarios from fixture directories.

Scans benchmark/fixtures/<category>/<testN>/ and generates a YAML scenario
for each one. The agent gets a minimal prompt: "here are the files, recreate
this in Dataiku."

Usage:
    python -m benchmark.generate_fixtures
    python -m benchmark.generate_fixtures --output benchmark/scenarios/auto_fixtures.yaml
    python -m benchmark.generate_fixtures --category alteryx
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Generic prompts per category — the agent figures out the rest
CATEGORY_PROMPTS = {
    "alteryx": """I'm migrating from Alteryx to Dataiku. Here are the files from an Alteryx workflow:

{file_list}

All files are in: {fixture_dir}

{spec_hint}

Recreate this workflow in Dataiku project {{project}}:
1. Upload the data files as datasets
2. Read any spec or documentation files to understand what the workflow does
3. Build the equivalent pipeline using Dataiku visual recipes where possible
4. Only use Python recipes when there's no visual recipe equivalent
5. Build everything and verify the output with `dku dataset head`

Show me the flow when you're done.""",
    "excel": """I have an Excel workbook that a business analyst maintains manually. We want to automate it in Dataiku.

{file_list}

All files are in: {fixture_dir}

{spec_hint}

Recreate this in Dataiku project {{project}}:
1. Upload the raw data
2. Read any spec files to understand the formulas and calculations
3. Recreate each calculation as a Dataiku recipe (group, sort, pivot, etc.)
4. Only use Python for calculations that don't map to visual recipes
5. Build and verify the output

The goal is zero Excel dependency — all logic in the DSS flow.""",
    "pandas": """A data scientist has a Python script they run locally. We need to migrate it to Dataiku.

{file_list}

All files are in: {fixture_dir}

{spec_hint}

Recreate this in Dataiku project {{project}}:
1. Read the Python script to understand what it does
2. Upload the input data
3. Decompose each step into a separate Dataiku recipe
4. Use visual recipes (join, group, sort, distinct, filter) instead of Python where possible
5. Only use Python recipes for steps with no visual equivalent
6. Build the full pipeline and verify output

The point of migration is to maximize visual recipes.""",
    "sales": """Build a data pipeline from these files in Dataiku project {{project}}:

{file_list}

All files are in: {fixture_dir}

{spec_hint}

Upload the data, join related datasets, aggregate as appropriate, and produce
useful summary outputs. Use visual recipes (join, group, sort) — not Python.""",
    "healthcare": """Build a healthcare analytics pipeline in Dataiku project {{project}} from these files:

{file_list}

All files are in: {fixture_dir}

{spec_hint}

Upload all datasets, join them on common keys, and produce department-level
summary statistics. Use visual recipes wherever possible.""",
}

# Fallback for unknown categories
DEFAULT_PROMPT = """Recreate this data workflow in Dataiku project {{project}}.

{file_list}

All files are in: {fixture_dir}

{spec_hint}

Upload the data, build a pipeline using visual recipes where possible,
and verify the output. Only use Python when no visual recipe fits."""


def discover_fixtures(category: str | None = None) -> list[dict]:
    """Scan fixture directories and return metadata for each test set.

    Returns list of {category, test_name, path, files, spec_file}.
    """
    fixtures = []
    if not FIXTURES_DIR.is_dir():
        return fixtures

    categories = (
        [category]
        if category
        else [d.name for d in sorted(FIXTURES_DIR.iterdir()) if d.is_dir()]
    )

    for cat in categories:
        cat_dir = FIXTURES_DIR / cat
        if not cat_dir.is_dir():
            continue
        for test_dir in sorted(cat_dir.iterdir()):
            if not test_dir.is_dir():
                continue
            files = [f.name for f in test_dir.iterdir() if f.is_file()]
            if not files:
                continue

            # Find spec/documentation files
            spec_file = None
            for candidate in [
                "workflow_spec.md",
                "workbook_spec.md",
                "spec.md",
                "README.md",
            ]:
                if candidate in files:
                    spec_file = candidate
                    break

            # Find the script file for pandas migrations
            script_file = None
            for candidate in ["script.py", "pipeline.py", "etl.py"]:
                if candidate in files:
                    script_file = candidate
                    break

            fixtures.append(
                {
                    "category": cat,
                    "test_name": test_dir.name,
                    "path": f"{cat}/{test_dir.name}",
                    "files": files,
                    "spec_file": spec_file,
                    "script_file": script_file,
                }
            )

    return fixtures


def generate_scenario(fixture: dict) -> dict:
    """Generate a YAML scenario dict for a single fixture set."""
    cat = fixture["category"]
    test_name = fixture["test_name"]
    scenario_id = f"auto_{cat}_{test_name}"

    file_list = "Files:\n" + "\n".join(f"- {f}" for f in sorted(fixture["files"]))

    # Hint about spec files
    spec_hint = ""
    if fixture["spec_file"]:
        spec_hint = f"Read `{{fixture_dir}}/{fixture['spec_file']}` first — it describes what this workflow does."
    elif fixture["script_file"]:
        spec_hint = f"Read `{{fixture_dir}}/{fixture['script_file']}` first — it's the script to migrate."

    # Pick the prompt template
    template = CATEGORY_PROMPTS.get(cat, DEFAULT_PROMPT)
    prompt = template.format(
        file_list=file_list,
        fixture_dir="{fixture_dir}",
        spec_hint=spec_hint,
    )

    # Determine which commands we expect
    expected_commands = [
        {"pattern": "dku dataset create", "required": True},
        {"pattern": "dku dataset upload", "required": True},
        {"pattern": "dku recipe create", "required": True},
    ]

    # Add visual recipe expectation for non-pandas categories
    if cat in ("alteryx", "excel", "sales", "healthcare"):
        expected_commands.append(
            {
                "pattern": "dku recipe create-(join|group|sort|filter|window|pivot)",
                "required": False,
            }
        )

    return {
        "id": scenario_id,
        "tier": 10,
        "category": f"auto-{cat}",
        "tags": ["auto", "fixture", cat],
        "prompt": prompt,
        "needs_project": True,
        "timeout": 600,
        "fixtures": [{"path": fixture["path"], "inject_as": "filesystem"}],
        "expect": {
            "commands": expected_commands,
            "verify": [
                {"command": "dku recipe list -P {project} -o json", "expect_status": 0},
                {"command": "dku flow graph -P {project}", "expect_status": 0},
            ],
        },
        "rubric": {
            "command_correct": 1.0,
            "outcome_verified": 1.0,
            "efficiency": 0.2,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate benchmark scenarios from fixture directories"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="benchmark/scenarios/auto_fixtures.yaml",
        help="Output YAML file",
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Only generate for this category (e.g., alteryx, excel)",
    )
    args = parser.parse_args()

    fixtures = discover_fixtures(args.category)
    if not fixtures:
        print("  No fixtures found.")
        return

    scenarios = [generate_scenario(f) for f in fixtures]

    output = {"tests": scenarios}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write("# Auto-generated from benchmark/fixtures/ — do not edit manually.\n")
        f.write("# Regenerate with: python -m benchmark.generate_fixtures\n")
        f.write(
            f"# Generated {len(scenarios)} scenarios from {len(fixtures)} fixture sets.\n\n"
        )
        yaml.dump(
            output,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

    print(f"  Generated {len(scenarios)} scenarios from {len(fixtures)} fixture sets.")
    print(f"  Written to: {output_path}")
    for s in scenarios:
        tags = s.get("tags", [])
        print(f"    {s['id']:40s} tags={tags}")


if __name__ == "__main__":
    main()
