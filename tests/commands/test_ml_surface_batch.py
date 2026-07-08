"""Issues #236/#245/#237/#250 — ml help classification, failure surfacing,
ensemble verb, time-ordered splits."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def _mltask(patch_client):
    return patch_client.get_project("PROJ1").get_ml_task.return_value


def _settings_raw(patch_client):
    return _mltask(patch_client).get_settings.return_value.get_raw.return_value


# --- #236: spec help classifies arguments vs options ------------------------


def test_ml_deploy_help_separates_arguments_from_options():
    result = runner.invoke(app, ["ml", "deploy", "--help"])
    assert result.exit_code == 0
    spec = json.loads(result.output)
    assert [a["name"] for a in spec["arguments"]] == [
        "analysis_id",
        "mltask_id",
        "model_id",
    ]
    flags = {o for opt in spec["options"] for o in opt["opts"]}
    assert {"--name", "--train-dataset", "--project", "-P"} <= flags


def test_ml_create_prediction_help_options_not_empty():
    result = runner.invoke(app, ["ml", "create-prediction", "--help"])
    spec = json.loads(result.output)
    assert [a["name"] for a in spec["arguments"]] == ["dataset", "target"]
    option_names = {o["name"] for o in spec["options"]}
    assert {"prediction_type", "guess_policy", "backend", "project"} <= option_names


def test_other_group_help_unaffected():
    result = runner.invoke(app, ["dataset", "create", "--help"])
    spec = json.loads(result.output)
    assert spec["options"], "options must not be empty"
    assert all(a["opts"] == [] for a in spec["arguments"])
    assert all(o["opts"] for o in spec["options"])


# --- #245: FAILED model failure surfacing ------------------------------------

_STACK = (
    "com.dataiku.dip.exceptions.ProcessDiedException: at java.base/x.y(Z.java)\n"
    "Traceback (most recent call last):\n"
    '  File "kernel.py", line 12, in <module>\n'
    "ModuleNotFoundError: No module named 'gluonts'"
)


def test_details_failed_model_surfaces_failure(patch_client):
    details = _mltask(patch_client).get_trained_model_details.return_value
    details.get_raw.return_value = {
        "trainInfo": {
            "state": "FAILED",
            "failure": {
                "message": "Training failed",
                "detailedMessage": "Kernel died",
                "stackTraceStr": _STACK,
            },
        }
    }
    result = runner.invoke(app, ["ml", "details", "a1", "t1", "m1", "-P", "PROJ1"])
    assert result.exit_code == 0, result.output
    assert "Training failed" in result.output
    assert "No module named 'gluonts'" in result.output
    assert "ProcessDiedException" not in result.output
    details.get_performance_metrics.assert_not_called()


def test_details_failed_model_json(patch_client):
    details = _mltask(patch_client).get_trained_model_details.return_value
    details.get_raw.return_value = {
        "trainInfo": {"state": "FAILED", "failure": {"stackTraceStr": _STACK}}
    }
    result = runner.invoke(
        app, ["--format", "json", "ml", "details", "a1", "t1", "m1", "-P", "PROJ1"]
    )
    payload = json.loads(result.output)
    assert payload["state"] == "FAILED"
    assert payload["python_traceback"].startswith("Traceback (most recent call last)")


def test_details_done_model_still_shows_metrics(patch_client):
    result = runner.invoke(app, ["ml", "details", "a1", "t1", "m1", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "auc" in result.output


def test_models_shows_truncated_failure_for_failed_rows(patch_client):
    _mltask(patch_client).get_trained_model_snippet.return_value = {
        "algorithm": "GLUONTS_NPTS_FORECASTER",
        "sessionId": "s1",
        "evaluationMetric": "ROC_AUC",
        "trainInfo": {
            "state": "FAILED",
            "failure": {"message": "x" * 200},
        },
    }
    result = runner.invoke(app, ["ml", "models", "a1", "t1", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "failure" in result.output
    assert "x" * 119 + "…" in result.output
    assert "x" * 130 not in result.output


def test_models_failure_falls_back_to_stack_last_line(patch_client):
    _mltask(patch_client).get_trained_model_snippet.return_value = {
        "algorithm": "A",
        "sessionId": "s1",
        "evaluationMetric": "",
        "trainInfo": {"state": "FAILED", "failure": {"stackTraceStr": _STACK}},
    }
    result = runner.invoke(app, ["ml", "models", "a1", "t1", "-P", "PROJ1"])
    assert "No module named 'gluonts'" in result.output


def test_models_no_failure_column_when_all_done(patch_client):
    result = runner.invoke(app, ["ml", "models", "a1", "t1", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "failure" not in result.output


# --- #237: ensemble ----------------------------------------------------------


def test_ensemble_happy_path(patch_client):
    mltask = _mltask(patch_client)
    mltask.ensemble.return_value = "A-PROJ1-a1-t1-s2-pp1-m9"
    result = runner.invoke(
        app,
        [
            "ml",
            "ensemble",
            "a1",
            "t1",
            "--model",
            "m1",
            "--model",
            "m2",
            "--method",
            "proba_average",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    mltask.ensemble.assert_called_once_with(["m1", "m2"], "PROBA_AVERAGE")
    assert "A-PROJ1-a1-t1-s2-pp1-m9" in result.output
    assert "dku ml deploy" in result.output


def test_ensemble_average_rejected_for_classification(patch_client):
    _settings_raw(patch_client)["predictionType"] = "BINARY_CLASSIFICATION"
    result = runner.invoke(
        app,
        [
            "ml",
            "ensemble",
            "a1",
            "t1",
            "-m",
            "m1",
            "-m",
            "m2",
            "--method",
            "AVERAGE",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "regression-only" in result.output
    assert "PROBA_AVERAGE" in result.output
    _mltask(patch_client).ensemble.assert_not_called()


def test_ensemble_proba_average_rejected_for_regression(patch_client):
    _settings_raw(patch_client)["predictionType"] = "REGRESSION"
    result = runner.invoke(
        app,
        [
            "ml",
            "ensemble",
            "a1",
            "t1",
            "-m",
            "m1",
            "-m",
            "m2",
            "--method",
            "PROBA_AVERAGE",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "classification-only" in result.output
    _mltask(patch_client).ensemble.assert_not_called()


def test_ensemble_requires_two_models(patch_client):
    result = runner.invoke(
        app,
        ["ml", "ensemble", "a1", "t1", "-m", "m1", "--method", "VOTE", "-P", "PROJ1"],
    )
    assert result.exit_code == 1
    assert "at least two" in result.output


def test_ensemble_bad_method_exits_2(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "ensemble",
            "a1",
            "t1",
            "-m",
            "m1",
            "-m",
            "m2",
            "--method",
            "BLEND",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "proba_average" in result.output.lower()


def test_ensemble_failed_training_exits_1(patch_client):
    mltask = _mltask(patch_client)
    mltask.ensemble.return_value = "mid9"
    mltask.get_trained_model_snippet.return_value = {
        "trainInfo": {"state": "FAILED", "failure": {"message": "boom"}}
    }
    result = runner.invoke(
        app,
        [
            "ml",
            "ensemble",
            "a1",
            "t1",
            "-m",
            "m1",
            "-m",
            "m2",
            "--method",
            "MEDIAN",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "boom" in result.output


# --- #250: time-ordered split -------------------------------------------------


def test_set_split_order_by_with_kfold_refused(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-split",
            "a1",
            "t1",
            "--order-by",
            "d",
            "--kfold",
            "3",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "not compatible with time ordering" in result.output
    _mltask(patch_client).get_settings.assert_not_called()


def test_set_split_descending_requires_order_by(patch_client):
    result = runner.invoke(
        app, ["ml", "set-split", "a1", "t1", "--descending", "-P", "PROJ1"]
    )
    assert result.exit_code == 1
    assert "--order-by" in result.output


def test_set_split_order_by_and_no_order_exclusive(patch_client):
    result = runner.invoke(
        app,
        ["ml", "set-split", "a1", "t1", "--order-by", "d", "--no-order", "-P", "PROJ1"],
    )
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_set_split_order_by_preserves_ssd_selection(patch_client):
    settings = _mltask(patch_client).get_settings.return_value
    split = settings.get_raw.return_value["splitParams"]
    split["ssdSelection"] = {"samplingMethod": "FULL"}
    split_params = settings.get_split_params.return_value

    def _clobber(column, ascending=True):
        split["ssdSplitMode"] = "SORTED"
        split["ssdColumn"] = column
        split["ssdSelection"] = {
            "samplingMethod": "HEAD_SEQUENTIAL",
            "maxRecords": 100000,
        }

    split_params.set_time_ordering.side_effect = _clobber
    result = runner.invoke(
        app, ["ml", "set-split", "a1", "t1", "--order-by", "order_date", "-P", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    split_params.set_time_ordering.assert_called_once_with("order_date", ascending=True)
    assert split["ssdSelection"] == {"samplingMethod": "FULL"}
    settings.save.assert_called_once()


def test_set_split_order_by_descending(patch_client):
    settings = _mltask(patch_client).get_settings.return_value
    result = runner.invoke(
        app,
        [
            "ml",
            "set-split",
            "a1",
            "t1",
            "--order-by",
            "d",
            "--descending",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.get_split_params.return_value.set_time_ordering.assert_called_once_with(
        "d", ascending=False
    )


def test_set_split_order_by_refused_when_kfold_already_on(patch_client):
    settings = _mltask(patch_client).get_settings.return_value
    settings.get_raw.return_value["splitParams"]["kfold"] = True
    result = runner.invoke(
        app, ["ml", "set-split", "a1", "t1", "--order-by", "d", "-P", "PROJ1"]
    )
    assert result.exit_code == 1
    assert "--no-kfold" in result.output
    settings.save.assert_not_called()


def test_set_split_no_order(patch_client):
    settings = _mltask(patch_client).get_settings.return_value
    result = runner.invoke(
        app, ["ml", "set-split", "a1", "t1", "--no-order", "-P", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    settings.get_split_params.return_value.unset_time_ordering.assert_called_once()
    settings.save.assert_called_once()


def test_set_split_order_by_unknown_column(patch_client):
    settings = _mltask(patch_client).get_settings.return_value
    settings.get_split_params.return_value.set_time_ordering.side_effect = ValueError(
        "Feature nope doesn't exist"
    )
    result = runner.invoke(
        app, ["ml", "set-split", "a1", "t1", "--order-by", "nope", "-P", "PROJ1"]
    )
    assert result.exit_code == 3
    assert "does not exist" in result.output
    settings.save.assert_not_called()
