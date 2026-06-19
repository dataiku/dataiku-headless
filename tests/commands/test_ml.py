"""Tests for ml commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# --- create-prediction ---


def test_ml_create_prediction(patch_client):
    result = runner.invoke(
        app,
        ["ml", "create-prediction", "customers", "churn", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "ML task ready" in result.output
    patch_client.get_project("PROJ1").create_prediction_ml_task.assert_called_once_with(
        "customers",
        "churn",
        ml_backend_type="PY_MEMORY",
        guess_policy="DEFAULT",
        prediction_type=None,
        wait_guess_complete=True,
    )


def test_ml_create_prediction_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "ml",
            "create-prediction",
            "customers",
            "churn",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert '"analysis_id"' in result.output
    assert '"a1"' in result.output
    assert '"t1"' in result.output


def test_ml_create_prediction_with_type(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "create-prediction",
            "customers",
            "churn",
            "--type",
            "BINARY_CLASSIFICATION",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_prediction_ml_task.assert_called_once_with(
        "customers",
        "churn",
        ml_backend_type="PY_MEMORY",
        guess_policy="DEFAULT",
        prediction_type="BINARY_CLASSIFICATION",
        wait_guess_complete=True,
    )


# --- create-clustering ---


def test_ml_create_clustering(patch_client):
    result = runner.invoke(
        app,
        ["ml", "create-clustering", "customers", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "ML task ready" in result.output
    patch_client.get_project("PROJ1").create_clustering_ml_task.assert_called_once_with(
        "customers",
        ml_backend_type="PY_MEMORY",
        guess_policy="KMEANS",
        wait_guess_complete=True,
    )


# --- create-timeseries ---


def test_ml_create_timeseries(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "create-timeseries",
            "sales",
            "revenue",
            "date_col",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project(
        "PROJ1"
    ).create_timeseries_forecasting_ml_task.assert_called_once_with(
        "sales",
        "revenue",
        "date_col",
        timeseries_identifiers=None,
        guess_policy="TIMESERIES_DEFAULT",
        wait_guess_complete=True,
    )


def test_ml_create_timeseries_with_identifiers(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "create-timeseries",
            "sales",
            "revenue",
            "date_col",
            "--identifier",
            "store_id",
            "--identifier",
            "region",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project(
        "PROJ1"
    ).create_timeseries_forecasting_ml_task.assert_called_once_with(
        "sales",
        "revenue",
        "date_col",
        timeseries_identifiers=["store_id", "region"],
        guess_policy="TIMESERIES_DEFAULT",
        wait_guess_complete=True,
    )


# --- create-causal ---


def test_ml_create_causal(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "create-causal",
            "experiment",
            "outcome",
            "treatment_flag",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project(
        "PROJ1"
    ).create_causal_prediction_ml_task.assert_called_once_with(
        "experiment",
        "outcome",
        "treatment_flag",
        prediction_type=None,
        wait_guess_complete=True,
    )


# --- list ---


def test_ml_list(patch_client):
    result = runner.invoke(app, ["ml", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "a1" in result.output
    assert "PREDICTION" in result.output


def test_ml_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "ml", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["analysis_id"] == "a1"
    assert parsed[0]["mltask_id"] == "t1"


def test_ml_list_dict_payload(patch_client):
    """The live DSS endpoint returns {"mlTasks": [...]}, not a bare list."""
    proj = patch_client.get_project("PROJ1")
    proj.list_ml_tasks.return_value = {
        "mlTasks": [
            {
                "analysisId": "a2",
                "mlTaskId": "t2",
                "taskType": "CLUSTERING",
                "inputDataset": "ds1",
            },
        ]
    }
    result = runner.invoke(app, ["ml", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "a2" in result.output
    assert "CLUSTERING" in result.output


# --- status ---


def test_ml_status(patch_client):
    result = runner.invoke(app, ["ml", "status", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "False" in result.output  # guessing: False


def test_ml_status_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "ml", "status", "a1", "t1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["guessing"] is False


# --- train ---


def test_ml_train(patch_client):
    result = runner.invoke(app, ["ml", "train", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Trained 1/1 model(s) successfully" in result.output
    patch_client.get_project("PROJ1").get_ml_task("a1", "t1").train.assert_called_once()


def test_ml_train_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "ml", "train", "a1", "t1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert '"count": 1' in result.output
    assert '"model_ids"' in result.output
    assert '"succeeded": 1' in result.output


def test_ml_train_zero_models_exits_nonzero(patch_client):
    """Training that produces 0 models must exit non-zero — exit 0 would let an
    agent chain `ml train && ml deploy` march on and deploy nothing."""
    mltask = patch_client.get_project("PROJ1").get_ml_task("a1", "t1")
    mltask.train.return_value = []
    result = runner.invoke(app, ["ml", "train", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code != 0, result.output
    assert "0 models" in result.output


def test_ml_train_all_failed_exits_nonzero(patch_client):
    """When every trained model's trainInfo.state is FAILED (none reached DONE),
    train must exit non-zero rather than reporting success."""
    mltask = patch_client.get_project("PROJ1").get_ml_task("a1", "t1")
    mltask.train.return_value = ["m-failed-1", "m-failed-2"]
    mltask.get_trained_model_snippet.return_value = {
        "algorithm": "RANDOM_FOREST_CLASSIFICATION",
        "trainInfo": {"state": "FAILED"},
    }
    result = runner.invoke(app, ["ml", "train", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code != 0, result.output
    assert "failed" in result.output.lower()


def test_ml_train_snippet_lookup_error_exits_nonzero_without_model_failure_summary(
    patch_client,
):
    mltask = patch_client.get_project("PROJ1").get_ml_task("a1", "t1")
    mltask.train.return_value = ["m1"]
    mltask.get_trained_model_snippet.side_effect = RuntimeError("snippet unavailable")

    result = runner.invoke(app, ["ml", "train", "a1", "t1", "--project", "PROJ1"])

    combined = (result.stdout + result.stderr).lower()
    assert result.exit_code != 0, result.output
    assert "snippet unavailable" in combined
    assert "all 1 trained model(s) failed" not in combined


def test_ml_train_partial_success_exits_zero(patch_client):
    """As long as at least one model reaches DONE, train succeeds (exit 0)."""
    mltask = patch_client.get_project("PROJ1").get_ml_task("a1", "t1")
    mltask.train.return_value = ["m-done", "m-failed"]
    snippets = {
        "m-done": {"trainInfo": {"state": "DONE"}},
        "m-failed": {"trainInfo": {"state": "FAILED"}},
    }
    mltask.get_trained_model_snippet.side_effect = lambda **kw: snippets[kw["id"]]
    result = runner.invoke(app, ["ml", "train", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0, result.output
    assert "Trained 1/2 model(s) successfully" in result.output


def test_ml_train_no_wait(patch_client):
    result = runner.invoke(
        app, ["ml", "train", "a1", "t1", "--no-wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Training started" in result.output
    patch_client.get_project("PROJ1").get_ml_task(
        "a1", "t1"
    ).start_train.assert_called_once()


# --- models ---


def test_ml_models(patch_client):
    result = runner.invoke(app, ["ml", "models", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "RandomForest" in result.output


def test_ml_models_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "ml", "models", "a1", "t1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["algorithm"] == "RandomForest"


# --- details ---


def test_ml_details(patch_client):
    result = runner.invoke(
        app, ["ml", "details", "a1", "t1", "model1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "auc" in result.output


def test_ml_details_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "ml",
            "details",
            "a1",
            "t1",
            "model1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["auc"] == 0.92


# --- deploy ---


def test_ml_deploy(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "deploy",
            "a1",
            "t1",
            "model1",
            "--name",
            "ChurnModel",
            "--train-dataset",
            "customers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Deployed to flow" in result.output
    assert "sm1" in result.output


def test_ml_deploy_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "ml",
            "deploy",
            "a1",
            "t1",
            "model1",
            "--name",
            "ChurnModel",
            "--train-dataset",
            "customers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert '"savedModelId"' in result.output
    assert '"sm1"' in result.output
    assert '"train_recipe1"' in result.output


# --- redeploy ---


def test_ml_redeploy(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "redeploy",
            "a1",
            "t1",
            "model1",
            "--saved-model-id",
            "sm1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Redeployed" in result.output


def test_ml_redeploy_missing_target(patch_client):
    result = runner.invoke(
        app,
        ["ml", "redeploy", "a1", "t1", "model1", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "saved-model-id" in result.output or "recipe-name" in result.output


# --- settings ---


def test_ml_settings(patch_client):
    result = runner.invoke(app, ["ml", "settings", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["taskType"] == "PREDICTION"


# --- algorithms ---


def test_ml_algorithms(patch_client):
    result = runner.invoke(app, ["ml", "algorithms", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "RandomForest" in result.output
    assert "XGBoost" in result.output


def test_ml_algorithms_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "ml", "algorithms", "a1", "t1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    algos = {a["name"]: a["enabled"] for a in parsed}
    assert algos["RandomForest"] == "True"
    assert algos["XGBoost"] == "False"


# --- set-algorithm ---


def test_ml_set_algorithm(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-algorithm",
            "a1",
            "t1",
            "--disable-all",
            "--enable",
            "XGBoost",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "updated" in result.output
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    settings.disable_all_algorithms.assert_called_once()
    settings.set_algorithm_enabled.assert_called_with("XGBoost", True)
    settings.save.assert_called_once()


# --- set-features (bulk, transactional) ---


def test_ml_set_features_single_transactional_write(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-features",
            "a1",
            "t1",
            "--reject",
            "col_a,col_b",
            "--input",
            "col_c",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Set 3 feature role(s)" in result.output
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    # The whole point: ONE save for N features (not N saves that race).
    settings.save.assert_called_once()
    assert settings.get_feature_preprocessing.call_count == 3


def test_ml_set_features_requires_at_least_one_role(patch_client):
    result = runner.invoke(
        app, ["ml", "set-features", "a1", "t1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "No feature roles" in result.output


# --- delete ---


def test_ml_delete(patch_client):
    result = runner.invoke(
        app, ["ml", "delete", "a1", "t1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted ML task" in result.output
    patch_client.get_project("PROJ1").get_ml_task(
        "a1", "t1"
    ).delete.assert_called_once()


# ── models metrics + redeploy stale-input advisory ────────────────────────


def test_ml_models_surfaces_headline_metric(patch_client):
    """Table shows METRIC/SCORE so agents can pick the best model without
    N+1 `dku ml details` calls."""
    result = runner.invoke(app, ["ml", "models", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ROC_AUC" in result.output
    assert "0.92" in result.output


def test_ml_models_json_includes_all_snippet_metrics(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "ml", "models", "a1", "t1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    row = parsed[0]
    assert row["metric"] == "ROC_AUC"
    assert row["score"] == 0.92
    assert row["score_direction"] == "higher"
    assert row["rank_score"] == 0.92
    assert row["auc"] == 0.92
    assert row["f1"] == 0.9
    assert row["state"] == "DONE"


def test_ml_models_rank_score_handles_lower_is_better_metrics(patch_client):
    mltask = patch_client.get_project("PROJ1").get_ml_task("a1", "t1")
    mltask.get_trained_models_ids.return_value = ["model-worse", "model-better"]
    snippets = {
        "model-worse": {
            "algorithm": "LinearRegression",
            "sessionId": "s1",
            "evaluationMetric": "RMSE",
            "rmse": 2.0,
            "trainInfo": {"state": "DONE"},
        },
        "model-better": {
            "algorithm": "RandomForest",
            "sessionId": "s1",
            "evaluationMetric": "RMSE",
            "rmse": 1.25,
            "trainInfo": {"state": "DONE"},
        },
    }
    mltask.get_trained_model_snippet.side_effect = lambda **kwargs: snippets[
        kwargs["id"]
    ]

    result = runner.invoke(
        app, ["--format", "json", "ml", "models", "a1", "t1", "--project", "PROJ1"]
    )

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["score_direction"] == "lower"
    assert parsed[0]["rank_score"] == -2.0
    assert max(parsed, key=lambda row: row["rank_score"])["id"] == "model-better"


def test_ml_models_bool_score_excluded_consistently(patch_client):
    """A boolean-valued metric must render score='' AND rank_score='' — the two
    paths must agree (bool is a subclass of int, so it must be excluded in both,
    not rendered as round(True)=1 in the score column)."""
    mltask = patch_client.get_project("PROJ1").get_ml_task("a1", "t1")
    mltask.get_trained_models_ids.return_value = ["model-bool"]
    mltask.get_trained_model_snippet.side_effect = lambda **kwargs: {
        "algorithm": "RandomForest",
        "sessionId": "s1",
        "evaluationMetric": "ROC_AUC",
        "auc": True,  # pathological boolean metric value
        "trainInfo": {"state": "DONE"},
    }

    result = runner.invoke(
        app, ["--format", "json", "ml", "models", "a1", "t1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    row = json.loads(result.output)[0]
    assert row["score"] == ""
    assert row["rank_score"] == ""


def test_ml_set_feature_role_accepts_lowercase(patch_client):
    """case_sensitive=False: a lowercase --role must parse."""
    result = runner.invoke(
        app,
        [
            "ml",
            "set-feature",
            "a1",
            "t1",
            "some_col",
            "--role",
            "reject",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


def test_ml_redeploy_warns_on_stale_recipe_input(patch_client):
    """redeploy swaps the model version but not the recipe input — warn when
    the analysis dataset differs so a flow rebuild doesn't silently retrain
    on the old data."""
    proj = patch_client.get_project("PROJ1")
    proj.get_analysis.return_value.get_definition.return_value.get_raw.return_value = {
        "inputDatasetSmartName": "new_train_ds"
    }
    result = runner.invoke(
        app,
        [
            "ml",
            "redeploy",
            "a1",
            "t1",
            "model1",
            "--recipe-name",
            "train_model",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "still reads" in result.output
    assert "replace-input" in result.output


def test_ml_redeploy_warns_on_stale_recipe_input_dataset_field(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.get_analysis.return_value.get_definition.return_value.get_raw.return_value = {
        "inputDataset": "new_train_ds"
    }
    result = runner.invoke(
        app,
        [
            "ml",
            "redeploy",
            "a1",
            "t1",
            "model1",
            "--recipe-name",
            "train_model",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "still reads" in result.output
    assert "new_train_ds" in result.output


def test_ml_redeploy_quiet_when_inputs_match(patch_client):
    """No advisory when the training recipe already reads the right dataset."""
    proj = patch_client.get_project("PROJ1")
    proj.get_analysis.return_value.get_definition.return_value.get_raw.return_value = {
        "inputDataset": "train_ds"
    }
    result = runner.invoke(
        app,
        [
            "ml",
            "redeploy",
            "a1",
            "t1",
            "model1",
            "--recipe-name",
            "train_model",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "still reads" not in result.output


# --- set-params ---


def test_ml_set_params_grid_preserves_limit(patch_client):
    """Grid hyperparameters: only `values` is replaced; limit/gridMode survive."""
    result = runner.invoke(
        app,
        [
            "ml",
            "set-params",
            "a1",
            "t1",
            "--algorithm",
            "RANDOM_FOREST_CLASSIFICATION",
            "--set",
            "n_estimators=100",
            "--set",
            "max_tree_depth=30",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    algo = settings.get_algorithm_settings("RANDOM_FOREST_CLASSIFICATION")
    assert algo["n_estimators"]["values"] == [100]
    assert algo["n_estimators"]["limit"] == {"min": 1}  # the trap: must survive
    assert algo["n_estimators"]["gridMode"] == "EXPLICIT"
    assert algo["max_tree_depth"]["values"] == [30]
    settings.save.assert_called_once()


def test_ml_set_params_plain_array_hyperparameter(patch_client):
    """Clustering hyperparams are plain arrays (NOT grid dicts) — a comma
    list must become a JSON array, and a single value a one-element array.
    Regression: the scalar path once stringified k to "3,4" and DSS rejected
    the save with 'Expected BEGIN_ARRAY but was STRING'."""
    result = runner.invoke(
        app,
        [
            "ml",
            "set-params",
            "a1",
            "t1",
            "-a",
            "KMEANS",
            "--set",
            "k=3,4,5,6",
            "--set",
            "seed=42",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    algo = settings.get_algorithm_settings("KMEANS")
    assert algo["k"] == [3, 4, 5, 6]
    assert algo["seed"] == 42  # plain scalar assigned directly

    result = runner.invoke(
        app,
        [
            "ml",
            "set-params",
            "a1",
            "t1",
            "-a",
            "KMEANS",
            "--set",
            "k=4",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert algo["k"] == [4]  # single value on an array param stays an array


def test_ml_set_params_plain_string_value(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-params",
            "a1",
            "t1",
            "-a",
            "random_forest_classification",  # lowercase accepted
            "--set",
            "selection_mode=sqrt",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    algo = settings.get_algorithm_settings("RANDOM_FOREST_CLASSIFICATION")
    assert algo["selection_mode"] == "sqrt"


def test_ml_set_params_unknown_algorithm_lists_available(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-params",
            "a1",
            "t1",
            "-a",
            "NOT_AN_ALGO",
            "--set",
            "x=1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Unknown algorithm" in result.output
    assert "Available:" in result.output


def test_ml_set_params_unknown_param_lists_valid_keys(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-params",
            "a1",
            "t1",
            "-a",
            "KMEANS",
            "--set",
            "nope=1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not found on KMEANS" in result.output
    assert "Valid parameters:" in result.output
    # Nothing half-applied
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    settings.save.assert_not_called()


def test_ml_set_params_rejects_malformed_set(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-params",
            "a1",
            "t1",
            "-a",
            "KMEANS",
            "--set",
            "justakey",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "expected param=value" in result.output


def test_ml_set_params_nested_object_param_errors(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-params",
            "a1",
            "t1",
            "-a",
            "RANDOM_FOREST_CLASSIFICATION",
            "--set",
            "grid=1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "nested settings object" in result.output


# --- set-split ---


def test_ml_set_split_train_ratio(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-split",
            "a1",
            "t1",
            "--train-ratio",
            "0.7",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "0.8 -> 0.7" in result.output
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    assert settings.get_raw()["splitParams"]["ssdTrainingRatio"] == 0.7
    settings.save.assert_called_once()


def test_ml_set_split_kfold(patch_client):
    result = runner.invoke(
        app,
        ["ml", "set-split", "a1", "t1", "--kfold", "5", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    split = settings.get_raw()["splitParams"]
    assert split["kfold"] is True
    assert split["nFolds"] == 5


def test_ml_set_split_invalid_ratio(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-split",
            "a1",
            "t1",
            "--train-ratio",
            "1.5",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "between 0 and 1" in result.output


def test_ml_set_split_requires_a_flag(patch_client):
    result = runner.invoke(app, ["ml", "set-split", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "Nothing to change" in result.output


def test_ml_set_split_rejects_kfold_with_no_kfold(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-split",
            "a1",
            "t1",
            "--kfold",
            "5",
            "--no-kfold",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_ml_set_split_clustering_has_no_split(patch_client):
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    settings.get_raw.return_value = {"taskType": "CLUSTERING"}  # no splitParams
    result = runner.invoke(
        app,
        [
            "ml",
            "set-split",
            "a1",
            "t1",
            "--train-ratio",
            "0.7",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "no splitParams" in result.output


# --- set-feature --rescaling ---


def test_ml_set_feature_rescaling_none(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-feature",
            "a1",
            "t1",
            "amount",
            "--rescaling",
            "NONE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    feat = settings._feature_store["amount"]
    assert feat["rescaling"] == "NONE"  # string enum, not an object
    settings.save.assert_called_once()


def test_ml_set_feature_role_and_rescaling_together(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-feature",
            "a1",
            "t1",
            "amount",
            "--role",
            "INPUT",
            "--rescaling",
            "minmax",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    feat = settings._feature_store["amount"]
    assert feat["role"] == "INPUT"
    assert feat["rescaling"] == "MINMAX"
    settings.save.assert_called_once()


def test_ml_set_feature_rescaling_rejects_non_numeric(patch_client):
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    settings._feature_store["city"] = {"role": "INPUT", "type": "CATEGORY"}
    result = runner.invoke(
        app,
        [
            "ml",
            "set-feature",
            "a1",
            "t1",
            "city",
            "--rescaling",
            "NONE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "only applies to NUMERIC" in result.output
    settings.save.assert_not_called()


def test_ml_set_feature_requires_role_or_rescaling(patch_client):
    result = runner.invoke(
        app,
        ["ml", "set-feature", "a1", "t1", "amount", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "Nothing to change" in result.output
