"""Tests for `dataset infer-types`, the build --wait exit fix, and the
set-definition round-trip dropped-keys warning."""

from __future__ import annotations

import json

from dku_cli.commands.dataset import _infer_column_type
from dku_cli.helpers import unpersisted_key_paths
from tests.commands.dataset.helpers import app, runner

# --- _infer_column_type unit coverage ---


def test_infer_int():
    assert _infer_column_type(["1", "2", "-3"]) == ("bigint", "")


def test_infer_double():
    assert _infer_column_type(["1.5", "2", "3e2"]) == ("double", "")


def test_infer_boolean_mixed_case():
    assert _infer_column_type(["true", "FALSE", "True"]) == ("boolean", "")


def test_infer_leading_zero_stays_string():
    proposed, note = _infer_column_type(["01234", "456"])
    assert proposed == "string"
    assert "leading zeros" in note


def test_infer_bigint_overflow_stays_string():
    proposed, note = _infer_column_type(["99999999999999999999"])
    assert proposed == "string"
    assert "bigint range" in note


def test_infer_date_like_reported_not_retyped():
    proposed, note = _infer_column_type(["2026-01-01", "2026-02-15"])
    assert proposed == "string"
    assert "DateParser" in note


def test_infer_mixed_stays_string():
    assert _infer_column_type(["1", "abc"]) == ("string", "")


def test_infer_empty_values_stay_string():
    proposed, note = _infer_column_type(["", None, "  "])
    assert proposed == "string"
    assert "no non-empty" in note


def test_infer_nan_not_numeric():
    assert _infer_column_type(["nan", "1.0"])[0] == "string"


def test_infer_underscore_not_numeric():
    """Python int('1_000') parses — the regex must reject it."""
    assert _infer_column_type(["1_000"])[0] == "string"


# --- infer-types command ---


def _wire_string_dataset(patch_client, rows):
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset.return_value
    ds.get_definition.return_value = {
        "type": "UploadedFiles",
        "managed": True,
        "params": {},
        "schema": {
            "columns": [
                {"name": "amount", "type": "string"},
                {"name": "label", "type": "string"},
            ]
        },
    }
    ds.iter_rows.return_value = iter(rows)
    return ds


def test_infer_types_dry_run_proposes(patch_client):
    _wire_string_dataset(patch_client, [["1.5", "a"], ["2.0", "b"]])
    result = runner.invoke(app, ["dataset", "infer-types", "ds1", "-P", "PROJ1"])
    assert result.exit_code == 0, result.output
    assert "double" in result.output
    assert "--apply" in result.output  # dry-run points at the apply form


def test_infer_types_apply_writes_schema(patch_client):
    ds = _wire_string_dataset(patch_client, [["1.5", "a"], ["2.0", "b"]])
    result = runner.invoke(
        app, ["dataset", "infer-types", "ds1", "--apply", "-P", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    assert "amount→double" in result.output
    sent = ds.set_definition.call_args[0][0]
    types = {c["name"]: c["type"] for c in sent["schema"]["columns"]}
    assert types == {"amount": "double", "label": "string"}


def test_infer_types_nothing_to_infer(patch_client):
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset.return_value
    ds.get_definition.return_value = {
        "schema": {"columns": [{"name": "a", "type": "bigint"}]},
        "params": {},
    }
    result = runner.invoke(app, ["dataset", "infer-types", "ds1", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "nothing to infer" in result.output


def test_infer_types_unbuilt_dataset_errors(patch_client):
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset.return_value
    ds.get_definition.return_value = {"schema": {"columns": []}, "params": {}}
    result = runner.invoke(app, ["dataset", "infer-types", "ds1", "-P", "PROJ1"])
    assert result.exit_code != 0
    assert "never been built" in result.output


def test_infer_types_json_output(patch_client):
    _wire_string_dataset(patch_client, [["7", "x"]])
    result = runner.invoke(
        app, ["--format", "json", "dataset", "infer-types", "ds1", "-P", "PROJ1"]
    )
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    by_col = {r["column"]: r["proposed"] for r in rows}
    assert by_col["amount"] == "bigint"


# --- dataset build --wait exit semantics ---


def test_dataset_build_wait_failed_exits_nonzero(patch_client):
    """`dataset build --wait` on a FAILED build must exit non-zero.

    Agents chain `dataset build --wait && next-step`; exit 0 on FAILED lets
    the chain march on past a broken build (sibling of the job run fix)."""
    proj = patch_client.get_project("PROJ1")
    job = proj.new_job.return_value.start.return_value
    job.get_status.return_value = {"baseStatus": {"state": "FAILED"}}
    result = runner.invoke(app, ["dataset", "build", "ds1", "--wait", "-P", "PROJ1"])
    assert result.exit_code != 0
    assert "FAILED" in result.output
    assert "job log" in result.output


def test_dataset_build_wait_done_emits_summary(patch_client):
    result = runner.invoke(app, ["dataset", "build", "ds1", "--wait", "-P", "PROJ1"])
    assert result.exit_code == 0, result.output
    assert "Built ds1:" in result.output


def test_dataset_build_wait_no_verify_skips_summary(patch_client):
    result = runner.invoke(
        app,
        ["dataset", "build", "ds1", "--wait", "--no-verify", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Built ds1:" not in result.output


# --- set-definition round-trip dropped-keys warning ---


def test_unpersisted_key_paths_helper():
    sent = {"a": 1, "params": {"good": 1, "bogus": 2}, "gone": {"x": 1}}
    persisted = {"a": "normalized", "params": {"good": 2}, "extra": True}
    assert unpersisted_key_paths(sent, persisted) == ["params.bogus", "gone"]


def test_unpersisted_skips_list_contents():
    sent = {"schema": {"columns": [{"name": "a"}]}}
    persisted = {"schema": {"columns": []}}
    assert unpersisted_key_paths(sent, persisted) == []


def test_set_definition_warns_on_dropped_keys(patch_client):
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset.return_value
    # Re-read after save does NOT contain the bogus key the user sent.
    ds.get_definition.return_value = {"type": "UploadedFiles", "params": {}}
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-definition",
            "ds1",
            "-d",
            '{"type": "UploadedFiles", "bogusKey": 1, "params": {"alsoBogus": 2}}',
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "NOT persisted" in result.output
    assert "bogusKey" in result.output
    assert "params.alsoBogus" in result.output


def test_set_definition_no_warning_when_all_persisted(patch_client):
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset.return_value
    ds.get_definition.return_value = {"type": "UploadedFiles", "params": {"x": 1}}
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-definition",
            "ds1",
            "-d",
            '{"type": "UploadedFiles", "params": {"x": 1}}',
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "NOT persisted" not in result.output


def test_set_definition_strips_smart_name(patch_client):
    """A get-definition -> set-definition round-trip carries smartName back;
    it's DSS-computed and must be dropped, not sent or flagged as unpersisted."""
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset.return_value
    ds.get_definition.return_value = {"type": "UploadedFiles", "params": {}}
    result = runner.invoke(
        app,
        [
            "dataset",
            "set-definition",
            "ds1",
            "-d",
            '{"type": "UploadedFiles", "smartName": "PROJ1.ds1", "params": {}}',
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "NOT persisted" not in result.output
    sent = ds.set_definition.call_args[0][0]
    assert "smartName" not in sent
