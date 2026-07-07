"""webapp cluster surf tests.

#192 — `dku webapp logs --crash` flag exists; no redundant --raw.
#188 — stopped backend with no logs stays neutral; failed start hints image build.

(#180 `webapp delete` was dropped: DSS 14.6 exposes no API-key-accessible
webapp deletion — DELETE→405, internal→401 — so no command was shipped.)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.commands.webapp import app

runner = CliRunner()


# ── #192: logs --crash flag exists, no --raw ─────────────────────────────


def test_logs_has_crash_flag_and_no_raw():
    result = runner.invoke(app, ["logs", "--help"])
    assert result.exit_code == 0, result.output
    assert "--crash" in result.output
    assert "--raw" not in result.output


# ── #188: clean stopped backend does not imply unbuilt image ─────────────


class _State:
    def __init__(self, state, running):
        self.state = state
        self.running = running


def test_logs_empty_tail_not_running_is_neutral(monkeypatch):
    webapp = MagicMock()
    webapp.get_state.return_value = _State({}, False)
    proj = MagicMock()
    proj.get_webapp.return_value = webapp
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.webapp.get_client_from_ctx", lambda ctx: client
    )
    result = runner.invoke(app, ["logs", "wid", "-P", "PROJ"])
    assert result.exit_code != 0
    assert "backend is not running" in result.output
    assert "code-env image may not be built" not in result.output
    assert "code-env update-images" not in result.output


# ── #262: create --from-plugin type-swap ─────────────────────────────────


def _create_client(monkeypatch):
    raw = {"type": "STANDARD", "params": {"backendEnabled": False}}
    settings = MagicMock()
    settings.get_raw.return_value = raw
    webapp = MagicMock()
    webapp.webapp_id = "wid1"
    webapp.get_settings.return_value = settings
    proj = MagicMock()
    proj.create_webapp.return_value = webapp
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.webapp.get_client_from_ctx", lambda ctx: client
    )
    return proj, settings, raw


def test_create_from_plugin_type_swap(monkeypatch):
    proj, settings, raw = _create_client(monkeypatch)
    result = runner.invoke(
        app,
        [
            "create",
            "myapp",
            "-P",
            "PROJ",
            "--from-plugin",
            "traces-explorer",
            "--component",
            "traces-explorer",
            "--config",
            '{"k": "v"}',
        ],
    )
    assert result.exit_code == 0, result.output
    proj.create_webapp.assert_called_once_with("myapp", webapp_type="STANDARD")
    assert raw["type"] == "webapp_traces-explorer_traces-explorer"
    assert raw["config"] == {"k": "v"}
    assert raw["params"]["backendEnabled"] is True
    settings.save.assert_called_once()


def test_create_from_plugin_requires_component(monkeypatch):
    _create_client(monkeypatch)
    result = runner.invoke(app, ["create", "x", "-P", "PROJ", "--from-plugin", "p"])
    assert result.exit_code != 0
    assert "--component" in result.output


def test_create_config_requires_from_plugin(monkeypatch):
    _create_client(monkeypatch)
    result = runner.invoke(app, ["create", "x", "-P", "PROJ", "--config", "{}"])
    assert result.exit_code != 0
    assert "--from-plugin" in result.output


def test_create_type_conflicts_with_from_plugin(monkeypatch):
    _create_client(monkeypatch)
    result = runner.invoke(
        app,
        [
            "create",
            "x",
            "-P",
            "PROJ",
            "--from-plugin",
            "p",
            "--component",
            "c",
            "-t",
            "DASH",
        ],
    )
    assert result.exit_code != 0
    assert "--type cannot be combined" in result.output


# ── #262: start tolerates HTTP 204 empty body from restart endpoint ──────


def test_start_tolerates_204_empty_body(monkeypatch):
    webapp = MagicMock()
    webapp.start_or_restart_backend.side_effect = ValueError(
        "Expecting value: line 1 column 1 (char 0)"
    )
    proj = MagicMock()
    proj.get_webapp.return_value = webapp
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.webapp.get_client_from_ctx", lambda ctx: client
    )
    result = runner.invoke(app, ["start", "wid", "-P", "PROJ"])
    assert result.exit_code == 0, result.output
    assert "Started" in result.output


# ── #231: status surfaces extra state and the Running caveat ─────────────


def test_status_running_shows_caveat_and_extras(monkeypatch):
    state = {
        "futureInfo": {
            "alive": True,
            "payload": {"extras": {"crashCount": 2}},
        },
        "hasExposedEndpoint": True,
        "exposed": {
            "expositionType": "local_process",
            "scheme": "http",
            "host": "127.0.0.1",
            "port": 5000,
        },
    }
    webapp = MagicMock()
    webapp.get_state.return_value = _State(state, True)
    proj = MagicMock()
    proj.get_webapp.return_value = webapp
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.webapp.get_client_from_ctx", lambda ctx: client
    )
    result = runner.invoke(app, ["status", "wid", "-P", "PROJ"])
    assert result.exit_code == 0, result.output
    assert '"crashCount":2' in result.output
    assert "http://127.0.0.1:5000" in result.output
    assert "not container scheduling" in result.output


def test_status_help_states_running_semantics():
    result = runner.invoke(app, ["status", "--help"])
    assert result.exit_code == 0
    assert "container scheduling" in result.output
