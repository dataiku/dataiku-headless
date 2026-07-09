"""Tests for helpers module."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

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
    project._fetch_evaluation_stores.side_effect = [
        [],
        [{"id": "mes9", "name": "LLM Evals", "mesFlavor": "LLM"}],
        [{"id": "agent9", "name": "Agent Evals", "mesFlavor": "AGENT"}],
    ]

    resolved = resolve_build_output_types(
        project,
        ["ds1", "fold1", "model1", "kb123", "My KB", "mes9", "Agent Evals"],
    )
    assert resolved == [
        ("ds1", "DATASET"),
        ("fold1", "MANAGED_FOLDER"),
        ("model1", "SAVED_MODEL"),
        ("kb123", "RETRIEVABLE_KNOWLEDGE"),
        ("kb123", "RETRIEVABLE_KNOWLEDGE"),
        ("mes9", "MODEL_EVALUATION_STORE"),
        ("agent9", "MODEL_EVALUATION_STORE"),
    ]
    assert project._fetch_evaluation_stores.call_args_list == [
        call(flavor="TABULAR"),
        call(flavor="LLM"),
        call(flavor="AGENT"),
    ]


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


# ── mutate_settings / object_write_lock (lost-update protection) ────────


class _FakeSettings:
    """Stand-in for a DSS *Settings object: raw dict + save recorder."""

    def __init__(self, version: int | None = None):
        self.data: dict = {"items": []}
        if version is not None:
            self.data["versionTag"] = {"versionNumber": version}
        self.saved = False

    def get_raw(self):
        return self.data

    def save(self):
        self.saved = True


def _client():
    client = MagicMock()
    client.host = "http://dss.example:11200"
    return client


def test_mutate_settings_saves_once_without_version_tag():
    from dku_cli.helpers import mutate_settings

    settings = _FakeSettings()
    fetch = MagicMock(return_value=settings)

    result = mutate_settings(
        _client(),
        "PROJ",
        "scenario",
        "scen1",
        fetch=fetch,
        mutate=lambda s: s.data["items"].append("a") or "ok",
    )

    assert result == "ok"
    assert settings.saved
    assert settings.data["items"] == ["a"]
    # No versionTag → no conflict probe, a single fetch.
    fetch.assert_called_once()


def test_mutate_settings_saves_when_version_unchanged():
    from dku_cli.helpers import mutate_settings

    settings = _FakeSettings(version=7)
    probe = _FakeSettings(version=7)
    fetch = MagicMock(side_effect=[settings, probe])

    mutate_settings(
        _client(),
        "PROJ",
        "scenario",
        "scen1",
        fetch=fetch,
        mutate=lambda s: s.data["items"].append("a"),
    )

    assert settings.saved
    assert not probe.saved
    assert fetch.call_count == 2


def test_mutate_settings_reapplies_mutation_on_concurrent_write():
    from dku_cli.helpers import mutate_settings

    stale = _FakeSettings(version=1)
    conflict_probe = _FakeSettings(version=2)  # someone else wrote meanwhile
    fresh = _FakeSettings(version=2)
    clean_probe = _FakeSettings(version=2)
    fetch = MagicMock(side_effect=[stale, conflict_probe, fresh, clean_probe])

    result = mutate_settings(
        _client(),
        "PROJ",
        "scenario",
        "scen1",
        fetch=fetch,
        mutate=lambda s: s.data["items"].append("a") or len(s.data["items"]),
    )

    # The stale document is never PUT over the concurrent write; the mutation
    # is re-applied to the freshly fetched one.
    assert not stale.saved
    assert fresh.saved
    assert fresh.data["items"] == ["a"]
    assert result == 1


def test_mutate_settings_exits_loudly_when_conflict_persists(capsys):
    from dku_cli.helpers import mutate_settings

    versions = iter(range(100))
    fetch = MagicMock(side_effect=lambda: _FakeSettings(version=next(versions)))

    with pytest.raises(SystemExit) as exc:
        mutate_settings(
            _client(),
            "PROJ",
            "scenario",
            "scen1",
            fetch=fetch,
            mutate=lambda s: None,
        )

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "scenario 'scen1'" in err
    assert "sequentially" in err


def test_object_write_lock_blocks_second_holder(monkeypatch, capsys):
    from dku_cli.helpers import object_write_lock

    monkeypatch.setattr("dku_cli.helpers._LOCK_TIMEOUT_S", 0.05)
    monkeypatch.setattr("dku_cli.helpers._LOCK_POLL_S", 0.01)

    client = _client()
    with object_write_lock(client, "PROJ", "scenario", "scen1"):
        with pytest.raises(SystemExit) as exc:
            with object_write_lock(client, "PROJ", "scenario", "scen1"):
                pass

    assert exc.value.code == 1
    assert "write lock" in capsys.readouterr().err


def test_object_write_lock_allows_per_call_timeout_override(monkeypatch, capsys):
    from dku_cli.helpers import object_write_lock

    monkeypatch.setattr("dku_cli.helpers._LOCK_TIMEOUT_S", 5.0)
    monkeypatch.setattr("dku_cli.helpers._LOCK_POLL_S", 0.01)

    client = _client()
    with object_write_lock(client, "PROJ", "scenario", "scen1"):
        with pytest.raises(SystemExit) as exc:
            with object_write_lock(client, "PROJ", "scenario", "scen1", timeout_s=0.05):
                pass

    assert exc.value.code == 1
    assert "Timed out after 0.05s" in capsys.readouterr().err


def test_object_write_lock_is_per_object(monkeypatch):
    from dku_cli.helpers import object_write_lock

    monkeypatch.setattr("dku_cli.helpers._LOCK_TIMEOUT_S", 0.05)

    client = _client()
    # A different object on the same host/project must not contend.
    with object_write_lock(client, "PROJ", "scenario", "scen1"):
        with object_write_lock(client, "PROJ", "scenario", "scen2"):
            pass


def test_object_write_lock_uses_backing_document_key_for_agents(monkeypatch, capsys):
    from dku_cli.helpers import object_write_lock

    monkeypatch.setattr("dku_cli.helpers._LOCK_TIMEOUT_S", 0.05)
    monkeypatch.setattr("dku_cli.helpers._LOCK_POLL_S", 0.01)

    client = _client()
    with object_write_lock(client, "PROJ", "agent", "sm1"):
        with pytest.raises(SystemExit) as exc:
            with object_write_lock(client, "PROJ", "saved-model", "sm1"):
                pass

    assert exc.value.code == 1
    assert "write lock" in capsys.readouterr().err


def test_object_write_lock_released_after_exit():
    from dku_cli.helpers import object_write_lock

    client = _client()
    with object_write_lock(client, "PROJ", "scenario", "scen1"):
        pass
    # Re-acquiring immediately must succeed — the lock was released.
    with object_write_lock(client, "PROJ", "scenario", "scen1"):
        pass


def test_locked_settings_saves_on_exit():
    from dku_cli.helpers import locked_settings

    settings = _FakeSettings(version=3)
    probe = _FakeSettings(version=3)
    fetch = MagicMock(side_effect=[settings, probe])

    with locked_settings(_client(), "PROJ", "recipe", "r1", fetch) as s:
        s.data["items"].append("a")

    assert settings.saved
    assert settings.data["items"] == ["a"]


def test_locked_settings_skips_save_when_body_raises():
    from dku_cli.helpers import locked_settings

    settings = _FakeSettings()
    with pytest.raises(SystemExit):
        with locked_settings(_client(), "PROJ", "recipe", "r1", lambda: settings):
            raise SystemExit(1)

    assert not settings.saved


def test_locked_settings_exits_loudly_on_concurrent_write(capsys):
    from dku_cli.helpers import locked_settings

    stale = _FakeSettings(version=1)
    probe = _FakeSettings(version=2)
    fetch = MagicMock(side_effect=[stale, probe])

    with pytest.raises(SystemExit):
        with locked_settings(_client(), "PROJ", "recipe", "r1", fetch) as s:
            s.data["items"].append("a")

    assert not stale.saved
    assert "another process" in capsys.readouterr().err


def test_locked_settings_forwards_timeout_override():
    from dku_cli.helpers import locked_settings

    client = _client()
    settings = _FakeSettings()

    @contextmanager
    def _stub_lock(*_args, **_kwargs):
        yield

    with patch(
        "dku_cli.helpers.object_write_lock", side_effect=_stub_lock
    ) as mock_lock:
        with locked_settings(
            client,
            "PROJ",
            "recipe",
            "r1",
            lambda: settings,
            timeout_s=90.0,
        ):
            pass

    assert settings.saved
    mock_lock.assert_called_once_with(client, "PROJ", "recipe", "r1", timeout_s=90.0)


def test_locked_settings_handles_settings_without_get_raw():
    from dku_cli.helpers import locked_settings

    class _NoRawSettings:
        # e.g. dataikuapi PrepareRecipeSettings — no get_raw(), no versionTag
        def __init__(self):
            self.saved = False

        def save(self):
            self.saved = True

    settings = _NoRawSettings()
    with locked_settings(_client(), "PROJ", "recipe", "r1", lambda: settings):
        pass

    assert settings.saved


def test_mutate_settings_forwards_timeout_override():
    from dku_cli.helpers import mutate_settings

    client = _client()
    settings = _FakeSettings()

    @contextmanager
    def _stub_lock(*_args, **_kwargs):
        yield

    with patch(
        "dku_cli.helpers.object_write_lock", side_effect=_stub_lock
    ) as mock_lock:
        mutate_settings(
            client,
            "PROJ",
            "scenario",
            "scen1",
            fetch=lambda: settings,
            mutate=lambda _: None,
            timeout_s=120.0,
        )

    mock_lock.assert_called_once_with(
        client, "PROJ", "scenario", "scen1", timeout_s=120.0
    )
