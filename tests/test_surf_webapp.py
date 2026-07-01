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
