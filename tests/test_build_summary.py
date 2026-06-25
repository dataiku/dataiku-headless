"""Unit tests for the post-build verification summary."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dku_cli.build_summary import (
    _PROBE_CAP,
    _fresh_metric_count,
    _probe_count,
    emit_build_summary,
    snapshot_schemas,
)


def _ds_with_metric(computed_ms, value="5"):
    ds = MagicMock()
    ds.get_last_metric_values.return_value.get_raw.return_value = {
        "metrics": [
            {
                "metric": {"id": "records:COUNT_RECORDS"},
                "lastValues": [{"computed": computed_ms, "value": value}],
            }
        ]
    }
    return ds


def test_fresh_metric_used_when_computed_after_job_start():
    ds = _ds_with_metric(computed_ms=1_000_000, value="42")
    assert _fresh_metric_count(ds, job_start_ms=999_000) == 42


def test_stale_metric_rejected():
    """A metric computed before the job started must NOT be trusted."""
    ds = _ds_with_metric(computed_ms=500_000, value="42")
    assert _fresh_metric_count(ds, job_start_ms=999_000) is None


def test_metric_missing_timestamp_rejected():
    ds = _ds_with_metric(computed_ms=None, value="42")
    assert _fresh_metric_count(ds, job_start_ms=0) is None


def test_probe_count_exact_below_cap():
    ds = MagicMock()
    ds.iter_rows.return_value = iter([["a"], ["b"], ["c"]])
    assert _probe_count(ds) == (3, True)


def test_probe_count_capped():
    ds = MagicMock()
    ds.iter_rows.return_value = iter([["x"]] * (_PROBE_CAP + 5))
    count, exact = _probe_count(ds)
    assert count == _PROBE_CAP
    assert exact is False


def _project_with_dataset(columns, rows, managed=True):
    proj = MagicMock()
    ds = MagicMock()
    ds.get_definition.return_value = {
        "managed": managed,
        "params": {},
        "schema": {"columns": columns},
    }
    # Stale metric so the probe path is exercised.
    ds.get_last_metric_values.return_value.get_raw.return_value = {"metrics": []}
    ds.iter_rows.return_value = iter(rows)
    proj.get_dataset.return_value = ds
    return proj, ds


def test_summary_success_line(capsys):
    proj, _ = _project_with_dataset(
        [{"name": "a", "type": "bigint"}, {"name": "b", "type": "string"}],
        [["1", "x"], ["2", "y"]],
    )
    emit_build_summary(MagicMock(), proj, "PROJ1", [("out", "DATASET")], 0)
    err = capsys.readouterr().err
    assert "Built out: 2 rows, 2 cols" in err


def test_summary_zero_rows_warns(capsys):
    proj, _ = _project_with_dataset([{"name": "a", "type": "string"}], [])
    emit_build_summary(MagicMock(), proj, "PROJ1", [("out", "DATASET")], 0)
    err = capsys.readouterr().err
    assert "0 rows" in err
    assert "empty output" in err
    assert "dku dataset head out -P PROJ1" in err


def test_summary_all_string_hint(capsys):
    proj, _ = _project_with_dataset(
        [{"name": "a", "type": "string"}, {"name": "b", "type": "string"}],
        [["1", "2"]],
    )
    emit_build_summary(MagicMock(), proj, "PROJ1", [("out", "DATASET")], 0)
    err = capsys.readouterr().err
    assert "typed string" in err
    assert "dku dataset infer-types out --apply -P PROJ1" in err


def test_summary_no_all_string_hint_when_typed(capsys):
    proj, _ = _project_with_dataset(
        [{"name": "a", "type": "bigint"}, {"name": "b", "type": "string"}],
        [["1", "x"]],
    )
    emit_build_summary(MagicMock(), proj, "PROJ1", [("out", "DATASET")], 0)
    assert "infer-types" not in capsys.readouterr().err


def test_summary_reports_added_column_vs_prev_schema(capsys):
    """With auto-update on, an applied schema change is reported, not silent."""
    proj, _ = _project_with_dataset(
        [{"name": "a", "type": "bigint"}, {"name": "b", "type": "string"}],
        [["1", "x"]],
    )
    emit_build_summary(
        MagicMock(),
        proj,
        "PROJ1",
        [("out", "DATASET")],
        0,
        prev_schemas={"out": {"a": "bigint"}},
    )
    err = capsys.readouterr().err
    assert "out: schema auto-updated" in err
    assert "added b" in err


def test_summary_reports_retyped_column(capsys):
    proj, _ = _project_with_dataset([{"name": "a", "type": "bigint"}], [["1"]])
    emit_build_summary(
        MagicMock(),
        proj,
        "PROJ1",
        [("out", "DATASET")],
        0,
        prev_schemas={"out": {"a": "string"}},
    )
    assert "retyped a string->bigint" in capsys.readouterr().err


def test_summary_no_delta_when_schema_unchanged(capsys):
    """No schema-change line when the build did not alter the schema."""
    cols = [{"name": "a", "type": "bigint"}, {"name": "b", "type": "string"}]
    proj, _ = _project_with_dataset(cols, [["1", "x"]])
    emit_build_summary(
        MagicMock(),
        proj,
        "PROJ1",
        [("out", "DATASET")],
        0,
        prev_schemas={"out": {"a": "bigint", "b": "string"}},
    )
    assert "schema auto-updated" not in capsys.readouterr().err


def test_summary_no_delta_without_prev_schemas(capsys):
    """No prev snapshot (e.g. opt-out) → no schema-change line."""
    proj, _ = _project_with_dataset([{"name": "a", "type": "bigint"}], [["1"]])
    emit_build_summary(MagicMock(), proj, "PROJ1", [("out", "DATASET")], 0)
    assert "schema auto-updated" not in capsys.readouterr().err


def test_snapshot_schemas_captures_types_and_skips_non_datasets():
    proj, _ = _project_with_dataset(
        [{"name": "a", "type": "bigint"}, {"name": "b", "type": "string"}], []
    )
    snap = snapshot_schemas(proj, [("out", "DATASET"), ("f", "MANAGED_FOLDER")])
    assert snap == {"out": {"a": "bigint", "b": "string"}}


def test_snapshot_schemas_never_raises():
    proj = MagicMock()
    proj.get_dataset.side_effect = RuntimeError("boom")
    assert snapshot_schemas(proj, [("out", "DATASET")]) == {}


def test_summary_skips_non_dataset_targets():
    proj = MagicMock()
    emit_build_summary(MagicMock(), proj, "PROJ1", [("folder1", "MANAGED_FOLDER")], 0)
    proj.get_dataset.assert_not_called()


def test_summary_never_raises(capsys):
    """A verification error must not fail a successful build."""
    proj = MagicMock()
    proj.get_dataset.side_effect = RuntimeError("boom")
    emit_build_summary(MagicMock(), proj, "PROJ1", [("out", "DATASET")], 0)
    assert "could not verify out" in capsys.readouterr().err


def test_summary_sql_count_path(capsys):
    """SQL-table-backed dataset uses SELECT COUNT(*) when the metric is stale."""
    proj = MagicMock()
    ds = MagicMock()
    ds.get_definition.return_value = {
        "managed": True,
        "params": {"connection": "sf", "table": "${projectKey}_OUT", "mode": "table"},
        "schema": {"columns": [{"name": "a", "type": "bigint"}]},
    }
    ds.get_last_metric_values.return_value.get_raw.return_value = {"metrics": []}
    proj.get_dataset.return_value = ds
    client = MagicMock()
    client.sql_query.return_value.iter_rows.return_value = iter([[7]])
    emit_build_summary(client, proj, "PROJ1", [("out", "DATASET")], 0)
    err = capsys.readouterr().err
    assert "Built out: 7 rows, 1 cols" in err
    sql = client.sql_query.call_args[0][0]
    assert sql == "SELECT COUNT(*) AS n FROM PROJ1_OUT"
    ds.iter_rows.assert_not_called()


@pytest.mark.parametrize("state_flag", ["--no-verify"])
def test_job_run_no_verify_skips_summary(patch_client, state_flag):
    from typer.testing import CliRunner

    from dku_cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["job", "run", "--target", "my_dataset", "--wait", state_flag, "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Built" not in result.output
