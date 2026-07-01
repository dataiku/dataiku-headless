"""Issues #178 / #183 / #193 — agent set-prompt/set-llm guards, set-llm
positional LLM id, and the new `agent rename` verb."""

from __future__ import annotations

from unittest.mock import MagicMock

import typer.main
from typer.testing import CliRunner

from dku_cli.commands.agent import app

runner = CliRunner()


def _params(command_name: str):
    """Return the click params of an agent subcommand (format-independent —
    avoids depending on whether --help renders rich text or JSON)."""
    cmd = typer.main.get_command(app).commands[command_name]
    return cmd.params


def _arg_names(command_name: str) -> set[str]:
    return {
        p.name
        for p in _params(command_name)
        if getattr(p, "param_type_name", None) == "argument"
    }


def _opt_flags(command_name: str) -> set[str]:
    return {
        opt
        for p in _params(command_name)
        if getattr(p, "param_type_name", None) == "option"
        for opt in getattr(p, "opts", [])
    }


class _VersionSettings:
    def __init__(self, raw):
        self._raw = raw

    def get_raw(self):
        return self._raw

    @property
    def llm_id(self):
        return self._raw.get("toolsUsingAgentSettings", {}).get("llmId")

    @llm_id.setter
    def llm_id(self, value):
        self._raw.setdefault("toolsUsingAgentSettings", {})["llmId"] = value


class _Settings:
    def __init__(self, raw):
        self._raw = raw
        self.saved = False

    def get_raw(self):
        return self._raw

    @property
    def active_version(self):
        return self._raw.get("activeVersion")

    @property
    def type(self):
        return self._raw["type"]

    def get_version_ids(self):
        return [v["versionId"] for v in self._raw["versions"]]

    def get_version_settings(self, version_id):
        for v in self._raw["versions"]:
            if v["versionId"] == version_id:
                return _VersionSettings(v)
        raise Exception(f"version {version_id} not found")

    def save(self):
        self.saved = True


class _Agent:
    def __init__(self, settings, agent_id="agent1"):
        self.id = agent_id
        self._settings = settings

    def get_settings(self):
        return self._settings


def _wire(monkeypatch, settings):
    agent = _Agent(settings)
    monkeypatch.setattr(
        "dku_cli.commands.agent.get_client_from_ctx", lambda ctx: MagicMock()
    )
    monkeypatch.setattr("dku_cli.commands.agent.resolve_agent", lambda proj, ref: agent)
    return agent


def _structured_no_loop_raw():
    return {
        "id": "agent1",
        "name": "myagent",
        "type": "STRUCTURED_AGENT",
        "projectKey": "PROJ1",
        "activeVersion": "v1",
        "versions": [{"versionId": "v1", "structuredAgentSettings": {"blocks": []}}],
    }


def _tools_using_raw():
    return {
        "id": "agent1",
        "name": "myagent",
        "type": "TOOLS_USING_AGENT",
        "projectKey": "PROJ1",
        "activeVersion": "v1",
        "versions": [{"versionId": "v1", "toolsUsingAgentSettings": {}}],
    }


# ── #183: set-llm takes the LLM id positionally ─────────────────────────


def test_set_llm_help_exposes_positional_llm_id():
    # The LLM id must be a positional argument (so `set-llm <agent> <llm_id>`
    # works), with --llm-id/--llm preserved as an option alias.
    args = _arg_names("set-llm")
    assert "llm_id" in args
    opt_flags = _opt_flags("set-llm")
    assert "--llm-id" in opt_flags


def test_set_llm_positional_parses_and_saves(monkeypatch):
    settings = _Settings(_tools_using_raw())
    _wire(monkeypatch, settings)
    result = runner.invoke(
        app, ["set-llm", "agent1", "openai:conn:gpt-4o", "-P", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    assert settings.saved is True
    assert (
        settings._raw["versions"][0]["toolsUsingAgentSettings"]["llmId"]
        == "openai:conn:gpt-4o"
    )


def test_set_llm_flag_alias_still_works(monkeypatch):
    settings = _Settings(_tools_using_raw())
    _wire(monkeypatch, settings)
    result = runner.invoke(
        app, ["set-llm", "agent1", "--llm-id", "openai:conn:gpt-4o", "-P", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    assert (
        settings._raw["versions"][0]["toolsUsingAgentSettings"]["llmId"]
        == "openai:conn:gpt-4o"
    )


def test_set_llm_missing_id_errors(monkeypatch):
    settings = _Settings(_tools_using_raw())
    _wire(monkeypatch, settings)
    result = runner.invoke(app, ["set-llm", "agent1", "-P", "PROJ1"])
    assert result.exit_code != 0
    assert settings.saved is False


# ── #178: set-prompt / set-llm guard on a loop-less structured agent ────


def test_set_prompt_structured_no_loop_blocks_with_prescriptive_error(monkeypatch):
    settings = _Settings(_structured_no_loop_raw())
    _wire(monkeypatch, settings)
    result = runner.invoke(
        app, ["set-prompt", "agent1", "--prompt", "hello", "-P", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "no loop block" in result.output
    assert "create-react" in result.output
    # Must NOT have persisted systemPromptAppend.
    assert settings.saved is False
    cfg = settings._raw["versions"][0]["structuredAgentSettings"]
    assert "systemPromptAppend" not in cfg


def test_set_llm_structured_no_loop_blocks_with_prescriptive_error(monkeypatch):
    settings = _Settings(_structured_no_loop_raw())
    _wire(monkeypatch, settings)
    result = runner.invoke(
        app, ["set-llm", "agent1", "openai:conn:gpt-4o", "-P", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "no loop block" in result.output
    assert "create-react" in result.output
    assert settings.saved is False
    cfg = settings._raw["versions"][0].get("structuredAgentSettings", {})
    assert "llmId" not in cfg


# ── #193: agent rename ───────────────────────────────────────────────────


class _SMSettings:
    def __init__(self, raw):
        self._raw = raw
        self.saved = False

    def get_raw(self):
        return self._raw

    def save(self):
        self.saved = True


class _SavedModel:
    """Backing saved model for an agent. Rename must go through this object's
    PUT (/projects/K/savedmodels/ID) — the agent-settings PUT drops `name`."""

    def __init__(self, raw):
        self._settings = _SMSettings(raw)

    def get_settings(self):
        return self._settings


def test_rename_sets_name_and_saves(monkeypatch):
    # The agent-settings save path is the wrong one (drops name). Rename must
    # write through the backing saved model and round-trip verify.
    sm_raw = {"id": "agent1", "name": "myagent", "savedModelType": "TOOLS_USING_AGENT"}
    saved_model = _SavedModel(sm_raw)
    proj = MagicMock()
    proj.get_saved_model.return_value = saved_model
    client = MagicMock()
    client.get_project.return_value = proj
    client.host = "https://dss.example"
    agent = _Agent(_Settings(_tools_using_raw()))
    monkeypatch.setattr(
        "dku_cli.commands.agent.get_client_from_ctx", lambda ctx: client
    )
    monkeypatch.setattr("dku_cli.commands.agent.resolve_agent", lambda proj, ref: agent)
    result = runner.invoke(app, ["rename", "agent1", "renamed_agent", "-P", "PROJ1"])
    assert result.exit_code == 0, result.output
    assert saved_model._settings.saved is True
    assert sm_raw["name"] == "renamed_agent"


def test_rename_help_exposes_args():
    args = _arg_names("rename")
    assert {"agent_ref", "new_name"} <= args
