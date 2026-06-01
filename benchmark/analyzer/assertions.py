"""Assertion registry for outcome-based benchmark checks."""

from __future__ import annotations

import itertools
import json
import math
from collections.abc import Callable

from benchmark.scenarios.schema import (
    Check,
    FlowShapeSpec,
    OutputDatasetSpec,
)


def _load_json(output: str):
    return json.loads(output or "null")


def _extract_columns(payload) -> set[str]:
    if isinstance(payload, dict):
        if "columns" in payload and isinstance(payload["columns"], list):
            return {
                col.get("name", "") if isinstance(col, dict) else str(col)
                for col in payload["columns"]
            }
        if "schema" in payload and isinstance(payload["schema"], dict):
            return _extract_columns(payload["schema"])
        if payload:
            first_value = next(iter(payload.values()))
            if isinstance(first_value, dict) and "type" in first_value:
                return set(payload.keys())
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            if "name" in payload[0]:
                return {str(item.get("name", "")) for item in payload}
            return set(payload[0].keys())
    return set()


def _find_column_type(payload, column: str) -> str:
    if isinstance(payload, dict):
        if "columns" in payload and isinstance(payload["columns"], list):
            for col in payload["columns"]:
                if isinstance(col, dict) and col.get("name") == column:
                    return str(col.get("type", ""))
        if "schema" in payload and isinstance(payload["schema"], dict):
            return _find_column_type(payload["schema"], column)
        if column in payload and isinstance(payload[column], dict):
            return str(payload[column].get("type", ""))
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("name") == column:
                return str(item.get("type", ""))
    return ""


AssertionFunc = Callable[..., tuple[bool, str]]


def check_has_columns(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    if exit_code != 0:
        return False, f"Command exited with {exit_code}"
    payload = _load_json(run_output)
    actual = _extract_columns(payload)
    missing = [column for column in check.columns if column not in actual]
    if missing:
        return False, f"Missing columns: {missing}"
    return True, ""


def check_min_rows(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    if exit_code != 0:
        return False, f"Command exited with {exit_code}"
    payload = _load_json(run_output)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("rows") or payload.get("data") or []
    else:
        rows = []
    if len(rows) < check.min:
        return False, f"Expected at least {check.min} rows, got {len(rows)}"
    return True, ""


def check_no_python_recipes(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    if exit_code != 0:
        return False, f"Command exited with {exit_code}"
    payload = _load_json(run_output)
    code_types = {"python", "r", "shell", "pyspark", "sparkr", "spark_scala"}
    code_recipes = [
        recipe.get("name", "?")
        for recipe in payload
        if isinstance(recipe, dict)
        and str(recipe.get("type", "")).lower() in code_types
    ]
    if code_recipes:
        return False, f"Found code recipes: {', '.join(code_recipes)}"
    return True, ""


def check_column_is_numeric(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    if exit_code != 0:
        return False, f"Command exited with {exit_code}"
    payload = _load_json(run_output)
    col_type = _find_column_type(payload, check.column).lower()
    numeric_tokens = {"int", "bigint", "smallint", "float", "double", "decimal", "long"}
    if not col_type:
        return False, f"Column '{check.column}' not found"
    if not any(token in col_type for token in numeric_tokens):
        return False, f"Column '{check.column}' has non-numeric type '{col_type}'"
    return True, ""


def check_exit_code_nonzero(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    if exit_code == 0:
        return False, "Expected non-zero exit code"
    return True, ""


def check_exit_code_zero(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    if exit_code != 0:
        return False, f"Expected zero exit code, got {exit_code}"
    return True, ""


def check_output_contains(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    if exit_code != 0:
        return False, f"Command exited with {exit_code}"
    needle = check.contains or check.column
    if needle not in run_output:
        return False, f"Expected output to contain '{needle}'"
    return True, ""


def _normalize_value(value):
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value) if "." in str(value) else int(value)
    except (ValueError, TypeError):
        return str(value).strip()


def _values_equal(a, b) -> bool:
    """Equality with float tolerance so summed doubles don't fail on the last digit."""
    na, nb = _normalize_value(a), _normalize_value(b)
    if isinstance(na, float) or isinstance(nb, float):
        try:
            return math.isclose(float(na), float(nb), rel_tol=1e-6, abs_tol=1e-2)
        except (TypeError, ValueError):
            return na == nb
    return na == nb


def _ordered_sample_mismatches(
    actual_rows: list[dict],
    expected_rows: list[dict],
    keys: list[str] | None = None,
    max_reported: int = 5,
) -> list[str]:
    """Compare rows in order — return up to max_reported mismatch descriptions."""
    mismatches: list[str] = []
    max_len = max(len(actual_rows), len(expected_rows))
    for i in range(max_len):
        if i >= len(actual_rows):
            mismatches.append(
                f"Row {i}: expected {expected_rows[i]}, got <end of data>"
            )
        elif i >= len(expected_rows):
            mismatches.append(f"Row {i}: expected <end>, got {actual_rows[i]}")
        else:
            actual = actual_rows[i]
            expected = expected_rows[i]
            for k in expected:
                if not _values_equal(actual.get(k), expected[k]):
                    ev = _normalize_value(expected[k])
                    av = _normalize_value(actual.get(k))
                    mismatches.append(f"Row {i} col '{k}': expected {ev!r}, got {av!r}")
                    break
        if len(mismatches) >= max_reported:
            break
    return mismatches


def _unordered_sample_mismatches(
    actual_rows: list[dict],
    expected_rows: list[dict],
    max_reported: int = 5,
) -> list[str]:
    """Match each expected row to any actual row — return mismatches."""
    mismatches: list[str] = []
    unmatched_actual = list(actual_rows)
    for ei, exp in enumerate(expected_rows):
        found = None
        for ai, act in enumerate(unmatched_actual):
            if all(_values_equal(act.get(k), v) for k, v in exp.items()):
                found = ai
                break
        if found is not None:
            unmatched_actual.pop(found)
        else:
            mismatches.append(f"Expected row {ei} not found: {exp}")
            if len(mismatches) >= max_reported:
                break
    return mismatches


def _keyed_sample_mismatches(
    actual_rows: list[dict],
    expected_rows: list[dict],
    key_columns: list[str],
    max_reported: int = 5,
) -> list[str]:
    """Match rows by key columns — return mismatches."""
    actual_by_key: dict[tuple, dict] = {}
    for row in actual_rows:
        k = tuple(_normalize_value(row.get(c)) for c in key_columns)
        actual_by_key[k] = row

    mismatches: list[str] = []
    for exp in expected_rows:
        k = tuple(_normalize_value(exp.get(c)) for c in key_columns)
        act = actual_by_key.get(k)
        if act is None:
            mismatches.append(f"Row with key {k!r} not found in actual data")
        else:
            for col, ev in exp.items():
                if not _values_equal(act.get(col), ev):
                    av = _normalize_value(act.get(col))
                    mismatches.append(
                        f"Row key {k!r} col '{col}': expected {ev!r}, got {av!r}"
                    )
                    break
        if len(mismatches) >= max_reported:
            break
    return mismatches


def _fetch_actual_schema(client, project_key: str, dataset_name: str) -> list[dict]:
    """Get actual schema columns from a DSS dataset."""
    ds = client.get_project(project_key).get_dataset(dataset_name)
    definition = ds.get_definition()
    schema = definition.get("schema", {})
    columns = schema.get("columns", [])
    return columns


def _fetch_actual_rows(
    client, project_key: str, dataset_name: str, limit: int = 100
) -> list[dict]:
    """Get actual data rows from a DSS dataset."""
    ds = client.get_project(project_key).get_dataset(dataset_name)
    rows: list[dict] = []
    for row in itertools.islice(ds.iter_rows(), limit):
        if isinstance(row, dict):
            rows.append(row)
        elif isinstance(row, (list, tuple)):
            # Row may be positional — need schema to map
            schema = _fetch_actual_schema(client, project_key, dataset_name)
            rows.append(
                {col["name"]: row[i] for i, col in enumerate(schema) if i < len(row)}
            )
    return rows


def check_output_schema(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    """Verify actual dataset schema matches expected_outputs schema exactly."""
    ctx = context or {}
    client = ctx.get("client")
    project_key = ctx.get("project_key")
    expected_outputs: dict[str, OutputDatasetSpec] = ctx.get("expected_outputs") or {}

    if not client or not project_key:
        return False, "No DSS client or project_key in context"

    dataset_name = check.columns[0] if check.columns else ""
    if not dataset_name:
        return False, "check.columns[0] must be the dataset name"

    expected = expected_outputs.get(dataset_name)
    if not expected:
        return False, f"No expected_outputs spec for dataset '{dataset_name}'"

    if not expected.schema_:
        return True, ""

    try:
        actual_cols = _fetch_actual_schema(client, project_key, dataset_name)
    except Exception as exc:
        return False, f"Failed to read schema for '{dataset_name}': {exc}"

    actual_by_name = {c["name"]: c.get("type", "") for c in actual_cols}
    mismatches: list[str] = []
    for spec_col in expected.schema_:
        actual_type = actual_by_name.get(spec_col.name)
        if actual_type is None:
            mismatches.append(f"Missing column '{spec_col.name}'")
        elif actual_type.lower() != spec_col.type.lower():
            mismatches.append(
                f"Column '{spec_col.name}': expected type '{spec_col.type}', got '{actual_type}'"
            )

    if mismatches:
        return False, "; ".join(mismatches[:5])
    return True, ""


def check_output_rows(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    """Verify sampled rows match expected data values."""
    ctx = context or {}
    client = ctx.get("client")
    project_key = ctx.get("project_key")
    expected_outputs: dict[str, OutputDatasetSpec] = ctx.get("expected_outputs") or {}

    if not client or not project_key:
        return False, "No DSS client or project_key in context"

    dataset_name = check.columns[0] if check.columns else ""
    if not dataset_name:
        return False, "check.columns[0] must be the dataset name"

    expected = expected_outputs.get(dataset_name)
    if not expected:
        return False, f"No expected_outputs spec for dataset '{dataset_name}'"

    if not expected.data and expected.row_count <= 0:
        return True, ""

    # Fetch one more than the expected count so over-production is detectable.
    fetch_limit = max(100, expected.row_count + 1) if expected.row_count > 0 else 100
    try:
        actual_rows = _fetch_actual_rows(
            client, project_key, dataset_name, limit=fetch_limit
        )
    except Exception as exc:
        return False, f"Failed to read rows for '{dataset_name}': {exc}"

    if expected.row_count > 0 and len(actual_rows) != expected.row_count:
        return (
            False,
            f"Dataset '{dataset_name}': expected {expected.row_count} rows, got {len(actual_rows)}",
        )

    if not expected.data:
        return True, ""

    key_columns = check.columns[1:] if len(check.columns) > 1 else []
    if key_columns:
        mismatches = _keyed_sample_mismatches(actual_rows, expected.data, key_columns)
    elif ctx.get("ordered", False):
        mismatches = _ordered_sample_mismatches(actual_rows, expected.data)
    else:
        mismatches = _unordered_sample_mismatches(actual_rows, expected.data)

    if mismatches:
        return False, f"Data mismatch for '{dataset_name}': " + "; ".join(
            mismatches[:5]
        )
    return True, ""


def _schema_signature(columns: list[dict]) -> frozenset[tuple[str, str]]:
    return frozenset(
        (col.get("name", ""), col.get("type", "").lower()) for col in columns
    )


def _collect_project_state(client, project_key: str) -> dict:
    """Collect all datasets and recipes from a DSS project."""
    proj = client.get_project(project_key)
    datasets_raw = proj.list_datasets()
    datasets: dict[str, dict] = {}
    for ds in datasets_raw:
        name = ds.get("name", "")
        try:
            ds_obj = proj.get_dataset(name)
            definition = ds_obj.get_definition()
            schema = definition.get("schema", {})
            columns = schema.get("columns", [])
        except Exception:
            columns = ds.get("schema", {}).get("columns", [])
        datasets[name] = {"name": name, "columns": columns}

    recipes_raw = proj.list_recipes()
    recipes: dict[str, dict] = {}
    for recipe in recipes_raw:
        name = recipe.get("name", "")
        recipes[name] = {
            "name": name,
            "type": recipe.get("type", ""),
        }

    try:
        flow = proj.get_flow()
        graph = flow.get_graph()
        flow_nodes = graph.nodes
    except Exception:
        flow_nodes = {}

    for node_id, node_data in flow_nodes.items():
        node_type = node_data.get("type", "")
        if node_type == "RUNNABLE_RECIPE":
            ref = node_data.get("ref", "")
            predecessors = node_data.get("predecessors", [])
            successors = node_data.get("successors", [])
            if ref in recipes:
                recipes[ref]["inputs"] = [p for p in predecessors if p and p != ref]
                recipes[ref]["outputs"] = [s for s in successors if s and s != ref]

    return {"datasets": datasets, "recipes": recipes}


def _candidate_dataset_names(
    node: dict,
    actual_datasets: dict[str, dict],
) -> list[str]:
    """Find actual datasets whose schema signature matches the expected node."""
    expected_sig = _schema_signature(node.get("schema_", node.get("schema", [])))
    if not expected_sig:
        return list(actual_datasets.keys())
    candidates: list[str] = []
    for name, ds in actual_datasets.items():
        actual_sig = _schema_signature(ds.get("columns", []))
        if actual_sig == expected_sig:
            candidates.append(name)
    return candidates


def _find_alias_assignment(
    expected_nodes: dict,
    expected_recipes: list[dict],
    actual_datasets: dict[str, dict],
    actual_recipes: dict[str, dict],
) -> dict[str, str] | None:
    """Backtracking assignment: map expected node aliases to actual dataset names."""
    alias_candidates: dict[str, list[str]] = {}
    for alias, node in expected_nodes.items():
        candidates = _candidate_dataset_names(node, actual_datasets)
        if not candidates:
            return None
        alias_candidates[alias] = candidates

    sorted_aliases = sorted(
        alias_candidates.keys(), key=lambda a: len(alias_candidates[a])
    )

    assignment: dict[str, str] = {}

    def backtrack(idx: int) -> bool:
        if idx == len(sorted_aliases):
            return _verify_recipe_connectivity(
                assignment, expected_recipes, actual_recipes
            )
        alias = sorted_aliases[idx]
        for candidate in alias_candidates[alias]:
            if candidate not in assignment.values():
                assignment[alias] = candidate
                if backtrack(idx + 1):
                    return True
                del assignment[alias]
        return False

    if backtrack(0):
        return assignment
    return None


def _verify_recipe_connectivity(
    alias_assignment: dict[str, str],
    expected_recipes: list[dict],
    actual_recipes: dict[str, dict],
) -> bool:
    """Check that actual recipes connect the assigned datasets as expected."""
    for exp_recipe in expected_recipes:
        exp_type = exp_recipe.get("type", "")
        exp_inputs = exp_recipe.get("inputs", [])
        exp_outputs = exp_recipe.get("outputs", [])

        exp_input_datasets = {alias_assignment.get(inp, inp) for inp in exp_inputs}
        exp_output_datasets = {alias_assignment.get(out, out) for out in exp_outputs}

        found = False
        for act_recipe in actual_recipes.values():
            if act_recipe.get("type", "").lower() != exp_type.lower():
                continue
            act_inputs = set(act_recipe.get("inputs", []))
            act_outputs = set(act_recipe.get("outputs", []))
            if act_inputs == exp_input_datasets and act_outputs == exp_output_datasets:
                found = True
                break

        if not found:
            return False
    return True


def check_flow_shape(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    """Verify flow topology using schema-signature backtracking."""
    ctx = context or {}
    client = ctx.get("client")
    project_key = ctx.get("project_key")
    expected_flow: FlowShapeSpec | None = ctx.get("expected_flow")

    if not client or not project_key:
        return False, "No DSS client or project_key in context"
    if expected_flow is None:
        return False, "No expected_flow spec in context"

    try:
        project_state = _collect_project_state(client, project_key)
    except Exception as exc:
        return False, f"Failed to read project state: {exc}"

    actual_datasets = project_state["datasets"]
    actual_recipes = project_state["recipes"]

    if expected_flow.exact_dataset_count:
        n_expected = len(expected_flow.nodes)
        n_actual = len(actual_datasets)
        if n_actual != n_expected:
            return (
                False,
                f"Expected {n_expected} datasets, found {n_actual}",
            )

    if expected_flow.exact_recipe_count:
        n_expected = len(expected_flow.recipes)
        n_actual = len(actual_recipes)
        if n_actual != n_expected:
            return (
                False,
                f"Expected {n_expected} recipes, found {n_actual}",
            )

    expected_nodes = {
        alias: {"schema_": [c.model_dump() for c in node.schema_]}
        for alias, node in expected_flow.nodes.items()
    }
    expected_recipes = [
        {
            "type": r.type,
            "inputs": r.inputs,
            "outputs": r.outputs,
        }
        for r in expected_flow.recipes
    ]

    match = _find_alias_assignment(
        expected_nodes,
        expected_recipes,
        actual_datasets,
        actual_recipes,
    )

    if match is None:
        return (
            False,
            "No dataset-to-schema mapping satisfies the expected recipe graph",
        )
    return True, ""


def check_trigger_watches(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    """Verify a trigger of the given type watches a named dataset, scoped to the trigger object."""
    if exit_code != 0:
        return False, f"Command exited with {exit_code}"
    payload = _load_json(run_output)
    triggers = payload.get("triggers", []) if isinstance(payload, dict) else []
    ttype = check.trigger_type or "ds_modified"
    dataset = check.dataset
    for trigger in triggers:
        if not isinstance(trigger, dict) or trigger.get("type") != ttype:
            continue
        if not dataset:
            return True, ""
        watches = trigger.get("params", {}).get("watches", [])
        if any(w.get("itemId") == dataset for w in watches):
            return True, ""
        if dataset in json.dumps(trigger):
            return True, ""
    return False, f"No '{ttype}' trigger watching dataset '{dataset}'"


def check_reporter_sends_email(
    run_output: str, exit_code: int, check: Check, context: dict | None = None
) -> tuple[bool, str]:
    """Verify a reporter of the given type sends to a named address, scoped to the reporter object."""
    if exit_code != 0:
        return False, f"Command exited with {exit_code}"
    payload = _load_json(run_output)
    reporters = payload.get("reporters", []) if isinstance(payload, dict) else []
    rtype = check.reporter_type or "mail-scenario"
    email = check.email
    for reporter in reporters:
        blob = json.dumps(reporter)
        if rtype in blob and (not email or email in blob):
            return True, ""
    return False, f"No '{rtype}' reporter sending to '{email}'"


ASSERTION_REGISTRY: dict[str, AssertionFunc] = {
    "has_columns": check_has_columns,
    "min_rows": check_min_rows,
    "no_python_recipes": check_no_python_recipes,
    "column_is_numeric": check_column_is_numeric,
    "exit_code_nonzero": check_exit_code_nonzero,
    "exit_code_zero": check_exit_code_zero,
    "output_contains": check_output_contains,
    "output_schema": check_output_schema,
    "output_rows": check_output_rows,
    "flow_shape": check_flow_shape,
    "trigger_watches": check_trigger_watches,
    "reporter_sends_email": check_reporter_sends_email,
}
