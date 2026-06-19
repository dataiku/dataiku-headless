"""Tests for helpers module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import typer

from dku_cli.helpers import (
    ALL_NODE_TYPES,
    PROJECT_NODE_TYPES,
    clean_llm_id,
    get_client_from_ctx,
    get_govern_client_from_ctx,
    require_node_type,
    resolve_project,
)


def test_clean_llm_id_strips_stray_quotes():
    assert clean_llm_id('"openai:conn:gpt-4o') == ("openai:conn:gpt-4o", True)
    assert clean_llm_id("'openai:conn:gpt-4o'") == ("openai:conn:gpt-4o", True)
    assert clean_llm_id("openai:conn:gpt-4o") == ("openai:conn:gpt-4o", False)


def test_resolve_project_flag():
    assert resolve_project("MYPROJ") == "MYPROJ"


def test_resolve_project_env(monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "ENVPROJ")
    assert resolve_project(None) == "ENVPROJ"


def test_resolve_project_config(monkeypatch):
    monkeypatch.delenv("DKU_PROJECT", raising=False)
    with patch("dku_cli.helpers.get_default_project", return_value="CFGPROJ"):
        assert resolve_project(None) == "CFGPROJ"


def test_resolve_project_missing(monkeypatch):
    monkeypatch.delenv("DKU_PROJECT", raising=False)
    with patch("dku_cli.helpers.get_default_project", return_value=None):
        with pytest.raises(typer.BadParameter):
            resolve_project(None)


def test_resolve_project_flag_takes_precedence(monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "ENVPROJ")
    assert resolve_project("FLAGPROJ") == "FLAGPROJ"


def test_get_client_from_ctx():
    ctx = MagicMock()
    ctx.obj = {"url": "https://dss.example.com", "api_key": "abc123"}
    with (
        patch("dku_cli.helpers.get_client") as mock_get,
        patch("dku_cli.helpers.resolve_node_type", return_value="DESIGN"),
    ):
        mock_get.return_value = MagicMock()
        get_client_from_ctx(ctx)
        mock_get.assert_called_once_with(
            url="https://dss.example.com", api_key="abc123"
        )


def test_get_client_from_ctx_empty_obj():
    ctx = MagicMock()
    ctx.obj = None
    with (
        patch("dku_cli.helpers.get_client") as mock_get,
        patch("dku_cli.helpers.resolve_node_type", return_value=None),
    ):
        mock_get.return_value = MagicMock()
        get_client_from_ctx(ctx)
        mock_get.assert_called_once_with()


def test_require_node_type_allows_matching():
    ctx = MagicMock()
    ctx.obj = {}
    with patch("dku_cli.helpers.resolve_node_type", return_value="DESIGN"):
        require_node_type(ctx, PROJECT_NODE_TYPES)  # no raise


def test_require_node_type_allows_unknown():
    """Legacy profiles (pre node-type tracking) are not blocked."""
    ctx = MagicMock()
    ctx.obj = {}
    with patch("dku_cli.helpers.resolve_node_type", return_value=None):
        require_node_type(ctx, PROJECT_NODE_TYPES)  # no raise


def test_require_node_type_refuses_govern():
    ctx = MagicMock()
    ctx.obj = {}
    with patch("dku_cli.helpers.resolve_node_type", return_value="GOVERN"):
        with pytest.raises(SystemExit) as exc:
            require_node_type(ctx, PROJECT_NODE_TYPES)
        assert exc.value.code == 4


def test_require_node_type_uses_flag_overrides_target_node():
    ctx = MagicMock()
    ctx.obj = {
        "profile": "design-profile",
        "url": "https://govern.example.com",
        "api_key": "abc",
    }
    with (
        patch(
            "dku_cli.helpers.resolve_auth",
            return_value=("https://govern.example.com", "abc"),
        ),
        patch("dku_cli.helpers.probe_node_type", return_value="GOVERN"),
        patch("dku_cli.helpers.resolve_node_type", return_value="DESIGN"),
    ):
        with pytest.raises(SystemExit) as exc:
            require_node_type(ctx, PROJECT_NODE_TYPES)
        assert exc.value.code == 4


def test_require_node_type_uses_env_overrides_target_node(monkeypatch):
    monkeypatch.setenv("DKU_URL", "https://design.example.com")
    monkeypatch.setenv("DKU_API_KEY", "secret")
    ctx = MagicMock()
    ctx.obj = {"profile": "govern-profile"}
    with (
        patch(
            "dku_cli.helpers.resolve_auth",
            return_value=("https://design.example.com", "secret"),
        ),
        patch("dku_cli.helpers.probe_node_type", return_value="DESIGN"),
        patch("dku_cli.helpers.resolve_node_type", return_value="GOVERN"),
    ):
        require_node_type(ctx, PROJECT_NODE_TYPES)


def test_get_govern_client_from_ctx_refuses_design():
    ctx = MagicMock()
    ctx.obj = {}
    with patch("dku_cli.helpers.resolve_node_type", return_value="DESIGN"):
        with pytest.raises(SystemExit):
            get_govern_client_from_ctx(ctx)


def test_get_govern_client_from_ctx_allows_govern():
    ctx = MagicMock()
    ctx.obj = {"url": "https://g.example.com", "api_key": "k"}
    with (
        patch("dku_cli.helpers.resolve_node_type", return_value="GOVERN"),
        patch("dku_cli.helpers.get_govern_client") as mock_get,
    ):
        mock_get.return_value = MagicMock()
        get_govern_client_from_ctx(ctx)
        mock_get.assert_called_once_with(url="https://g.example.com", api_key="k")


def test_get_client_from_ctx_blocks_wrong_node_type():
    """GOVERN profile is refused by default (project-scoped commands)."""

    ctx = MagicMock()
    ctx.obj = {"url": "https://govern.example.com", "api_key": "abc"}
    with (
        patch("dku_cli.helpers.get_client") as mock_get,
        patch("dku_cli.helpers.resolve_node_type", return_value="GOVERN"),
    ):
        mock_get.return_value = MagicMock()
        with pytest.raises(SystemExit):
            get_client_from_ctx(ctx)
        # Opt-in to ALL_NODE_TYPES lets it through.
        get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
        mock_get.assert_called_once()


def test_resolve_build_output_types_classifies_kb_and_eval_store():
    """KB outputs build as RETRIEVABLE_KNOWLEDGE, eval stores as
    MODEL_EVALUATION_STORE — the types the SDK's own build() methods post.
    Falling through to DATASET produced the misleading
    "dataset <id> does not exist" error on `dku recipe run`."""
    from dku_cli.helpers import resolve_build_output_types

    project = MagicMock()
    project.list_managed_folders.return_value = [{"id": "fold1", "name": "Folder"}]
    project.list_saved_models.return_value = [{"id": "model1", "name": "Model"}]
    project.list_knowledge_banks.return_value = [{"id": "kb123", "name": "My KB"}]
    project._fetch_evaluation_stores.return_value = [
        {"id": "mes9", "name": "Agent Evals", "mesFlavor": "LLM"}
    ]

    resolved = resolve_build_output_types(
        project, ["ds1", "fold1", "model1", "kb123", "My KB", "mes9", "Agent Evals"]
    )
    assert resolved == [
        ("ds1", "DATASET"),
        ("fold1", "MANAGED_FOLDER"),
        ("model1", "SAVED_MODEL"),
        ("kb123", "RETRIEVABLE_KNOWLEDGE"),
        ("kb123", "RETRIEVABLE_KNOWLEDGE"),
        ("mes9", "MODEL_EVALUATION_STORE"),
        ("mes9", "MODEL_EVALUATION_STORE"),
    ]
    project._fetch_evaluation_stores.assert_called_once_with(flavor=None)


def test_resolve_build_output_types_tolerates_missing_kb_mes_endpoints():
    """Older DSS without KB/eval-store endpoints must not break dataset builds."""
    from dku_cli.helpers import resolve_build_output_types

    project = MagicMock()
    project.list_managed_folders.return_value = []
    project.list_saved_models.return_value = []
    project.list_knowledge_banks.side_effect = Exception("404")
    project._fetch_evaluation_stores.side_effect = Exception("404")

    assert resolve_build_output_types(project, ["ds1"]) == [("ds1", "DATASET")]


def test_resolve_build_output_types_skips_kb_mes_for_plain_datasets():
    """The hot path (all refs are folders/models/datasets) must not pay the two
    expensive KB + eval-store round-trips — they are deferred until a ref isn't
    already a folder or saved model."""
    from dku_cli.helpers import resolve_build_output_types

    project = MagicMock()
    project.list_managed_folders.return_value = [{"id": "fold1", "name": "Folder"}]
    project.list_saved_models.return_value = [{"id": "model1", "name": "Model"}]
    project.list_datasets.return_value = [{"name": "ds1"}]

    resolved = resolve_build_output_types(project, ["ds1", "fold1", "model1"])
    assert resolved == [
        ("ds1", "DATASET"),
        ("fold1", "MANAGED_FOLDER"),
        ("model1", "SAVED_MODEL"),
    ]
    # ds1 short-circuits to DATASET via the cheap dataset list, so the two
    # expensive KB/eval-store lookups must NOT be issued.
    project.list_knowledge_banks.assert_not_called()
    project._fetch_evaluation_stores.assert_not_called()
