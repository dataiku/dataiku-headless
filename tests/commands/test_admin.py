"""Tests for admin commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_admin_logs(patch_client):
    result = runner.invoke(app, ["admin", "logs"])
    assert result.exit_code == 0
    assert "backend.log" in result.output


def test_admin_logs_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "admin", "logs"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "backend.log"


def test_admin_get_log(patch_client):
    result = runner.invoke(app, ["admin", "get-log", "backend.log"])
    assert result.exit_code == 0
    assert "DSS started" in result.output


def test_admin_usage(patch_client):
    result = runner.invoke(app, ["admin", "usage"])
    assert result.exit_code == 0
    assert "projects" in result.output
    assert "10" in result.output


def test_admin_usage_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "admin", "usage"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["projects"] == 10
    assert parsed["datasets"] == 50


def test_admin_instance_info(patch_client):
    result = runner.invoke(app, ["admin", "instance-info"])
    assert result.exit_code == 0
    assert "DESIGN" in result.output


def test_admin_instance_info_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "admin", "instance-info"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["nodeType"] == "DESIGN"
    assert parsed["dssVersion"] == "14.5.0"


def test_admin_sanity_check(patch_client):
    result = runner.invoke(app, ["admin", "sanity-check"])
    assert result.exit_code == 0
    assert "WARNING" in result.output
    assert "CHECK_001" in result.output


# =============================================================================
# admin license
# =============================================================================


def test_admin_license_status(patch_client):
    result = runner.invoke(app, ["admin", "license", "status"])
    assert result.exit_code == 0
    assert "ENTERPRISE" in result.output


def test_admin_license_upload_blocks_without_admin_flags(patch_client, tmp_path):
    f = tmp_path / "license.json"
    f.write_text('{"edition":"ENTERPRISE"}')
    result = runner.invoke(app, ["admin", "license", "upload", str(f), "--yes"])
    # Tier-4: --yes alone is not enough — needs --confirm-name + --i-know.
    assert result.exit_code == 77
    assert "BLOCKED" in result.output
    patch_client.set_license.assert_not_called()


def test_admin_license_upload_with_full_authorization(patch_client, tmp_path):
    f = tmp_path / "license.json"
    f.write_text('{"edition":"ENTERPRISE"}')
    result = runner.invoke(
        app,
        [
            "admin",
            "license",
            "upload",
            str(f),
            "--yes",
            "--confirm-name",
            "license",
            "--i-know-what-im-doing",
        ],
    )
    assert result.exit_code == 0
    patch_client.set_license.assert_called_once()


def test_admin_license_upload_missing_file(patch_client):
    result = runner.invoke(
        app, ["admin", "license", "upload", "/nonexistent.json", "--yes"]
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_admin_license_upload_invalid_json(patch_client, tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not-json")
    result = runner.invoke(app, ["admin", "license", "upload", str(f), "--yes"])
    assert result.exit_code == 1
    assert "valid JSON" in result.output or "not valid" in result.output.lower()


# =============================================================================
# admin sso / ldap / azure-ad
# =============================================================================


def test_admin_sso_get(patch_client):
    result = runner.invoke(app, ["admin", "sso", "get"])
    assert result.exit_code == 0
    assert "SAML" in result.output


def test_admin_sso_set_requires_definition(patch_client):
    result = runner.invoke(
        app, ["admin", "sso", "set", "--yes", "--i-understand-lockout-risk"]
    )
    assert result.exit_code == 1
    assert "definition" in result.output.lower()


def test_admin_sso_set_requires_lockout_ack(patch_client):
    result = runner.invoke(
        app,
        [
            "admin",
            "sso",
            "set",
            "-d",
            '{"enabled":true,"protocol":"SAML"}',
            "--yes",
        ],
    )
    assert result.exit_code == 1
    assert "lockout" in result.output.lower()
    patch_client.get_sso_settings.return_value.save.assert_not_called()


def test_admin_sso_set_blocks_without_admin_flags(patch_client):
    # Lockout ack present, but tier-4 still needs --yes + --confirm-name + --i-know.
    result = runner.invoke(
        app,
        [
            "admin",
            "sso",
            "set",
            "-d",
            '{"enabled":true}',
            "--i-understand-lockout-risk",
        ],
    )
    assert result.exit_code == 77
    assert "BLOCKED" in result.output
    patch_client.get_sso_settings.return_value.save.assert_not_called()


def test_admin_sso_set_applied(patch_client):
    result = runner.invoke(
        app,
        [
            "admin",
            "sso",
            "set",
            "-d",
            '{"enabled":true,"protocol":"SAML"}',
            "--yes",
            "--confirm-name",
            "sso",
            "--i-know-what-im-doing",
            "--i-understand-lockout-risk",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_sso_settings.return_value.save.assert_called_once()


def test_admin_sso_set_does_not_revert_openid_params(patch_client):
    """Regression: dataikuapi's SSOSettings.save() re-injects openIDParams /
    samlSPParams from instance attributes captured at construction. The CLI must
    refresh those instances from the new payload, otherwise a user's edits to
    exactly those two security-critical blocks are silently reverted on save."""
    saved = {}

    class FakeSSO:
        def __init__(self):
            # The live config the agent is editing.
            self.sso_settings = {
                "openIDParams": {"clientId": "OLD"},
                "samlSPParams": {},
            }
            # Instances captured from the ORIGINAL settings (the dataikuapi trap).
            self.openid_params_instance = dict(self.sso_settings["openIDParams"])
            self.saml_sp_params_instance = dict(self.sso_settings["samlSPParams"])

        def save(self):
            # Mirror dataikuapi SSOSettings.save(): re-inject from the instances.
            self.sso_settings["openIDParams"] = dict(self.openid_params_instance)
            self.sso_settings["samlSPParams"] = dict(self.saml_sp_params_instance)
            saved["body"] = self.sso_settings

    patch_client.get_sso_settings.return_value = FakeSSO()

    result = runner.invoke(
        app,
        [
            "admin",
            "sso",
            "set",
            "-d",
            '{"enabled":true,"protocol":"OPENID","openIDParams":{"clientId":"NEW"}}',
            "--yes",
            "--confirm-name",
            "sso",
            "--i-know-what-im-doing",
            "--i-understand-lockout-risk",
        ],
    )
    assert result.exit_code == 0, result.output
    # The NEW clientId must survive save(), not be reverted to OLD.
    assert saved["body"]["openIDParams"] == {"clientId": "NEW"}
    assert saved["body"]["enabled"] is True


def test_admin_ldap_get(patch_client):
    result = runner.invoke(app, ["admin", "ldap", "get"])
    assert result.exit_code == 0
    assert "ldap.example.com" in result.output


def test_admin_azure_ad_get(patch_client):
    patch_client.get_azure_ad_settings.return_value.azuread_settings = {
        "enabled": False,
        "tenantId": "t1",
    }
    result = runner.invoke(app, ["admin", "azure-ad", "get"])
    assert result.exit_code == 0
    assert "tenantId" in result.output


# =============================================================================
# admin settings
# =============================================================================


def test_admin_settings_get(patch_client):
    result = runner.invoke(app, ["admin", "settings", "get"])
    assert result.exit_code == 0
    assert "impersonation" in result.output


def test_admin_settings_set_blocks_without_admin_flags(patch_client):
    payload = (
        '{"dssVersion":"14.0.2","impersonation":{"rules":[]},"containerSettings":{}}'
    )
    result = runner.invoke(app, ["admin", "settings", "set", "-d", payload, "--yes"])
    # Tier-4: --yes alone is blocked.
    assert result.exit_code == 77
    assert "BLOCKED" in result.output
    patch_client.get_general_settings.return_value.save.assert_not_called()


_SETTINGS_ADMIN_FLAGS = [
    "--yes",
    "--confirm-name",
    "general-settings",
    "--i-know-what-im-doing",
]


def test_admin_settings_set_rejects_partial_payload(patch_client):
    # Missing 'containerSettings' and 'impersonation' — partial check runs after
    # the guard passes, so full tier-4 authorization is supplied here.
    partial = '{"dssVersion":"14.0.2"}'
    result = runner.invoke(
        app, ["admin", "settings", "set", "-d", partial, *_SETTINGS_ADMIN_FLAGS]
    )
    assert result.exit_code == 1
    assert "missing" in result.output.lower()
    patch_client.get_general_settings.return_value.save.assert_not_called()


def test_admin_settings_set_applied(patch_client):
    full = '{"dssVersion":"14.0.2","impersonation":{"rules":[]},"containerSettings":{}}'
    result = runner.invoke(
        app, ["admin", "settings", "set", "-d", full, *_SETTINGS_ADMIN_FLAGS]
    )
    assert result.exit_code == 0
    patch_client.get_general_settings.return_value.save.assert_called_once()


# =============================================================================
# admin users-sync
# =============================================================================


def test_admin_users_sync_resync_all_blocks_without_confirm_name(patch_client):
    # Tier-3 cascade: --yes alone is not enough.
    result = runner.invoke(app, ["admin", "users-sync", "resync-all", "--yes"])
    assert result.exit_code == 77
    assert "BLOCKED" in result.output
    patch_client.start_resync_all_users_from_supplier.assert_not_called()


def test_admin_users_sync_resync_all_yes(patch_client):
    result = runner.invoke(
        app,
        [
            "admin",
            "users-sync",
            "resync-all",
            "--yes",
            "--confirm-name",
            "resync-all",
        ],
    )
    assert result.exit_code == 0
    patch_client.start_resync_all_users_from_supplier.assert_called_once()


def test_admin_users_sync_fetch_external_users(patch_client):
    result = runner.invoke(
        app,
        ["admin", "users-sync", "fetch-external-users", "--source", "LDAP"],
    )
    assert result.exit_code == 0
    patch_client.start_fetch_external_users.assert_called_once()


def test_admin_users_sync_rejects_bad_source(patch_client):
    result = runner.invoke(
        app,
        ["admin", "users-sync", "fetch-external-users", "--source", "BOGUS"],
    )
    assert result.exit_code == 1
    assert "LDAP" in result.output


# =============================================================================
# admin messaging / infra / code-studio-template
# =============================================================================


def test_admin_messaging_list(patch_client):
    result = runner.invoke(app, ["admin", "messaging", "list"])
    assert result.exit_code == 0
    assert "ops-smtp" in result.output


def test_admin_messaging_create_requires_yes(patch_client):
    result = runner.invoke(
        app,
        [
            "admin",
            "messaging",
            "create",
            "--type",
            "smtp",
            "--config",
            '{"host":"smtp.example.com"}',
        ],
    )
    assert result.exit_code == 77
    assert "BLOCKED" in result.output
    patch_client.create_messaging_channel.assert_not_called()


def test_admin_messaging_create_yes(patch_client):
    result = runner.invoke(
        app,
        [
            "admin",
            "messaging",
            "create",
            "--type",
            "smtp",
            "--id",
            "ops-smtp",
            "--config",
            '{"host":"smtp.example.com"}',
            "--yes",
        ],
    )
    assert result.exit_code == 0
    patch_client.create_messaging_channel.assert_called_once()


def test_admin_infra_push_base_images_requires_yes(patch_client):
    result = runner.invoke(app, ["admin", "infra", "push-base-images"])
    assert result.exit_code == 77
    assert "BLOCKED" in result.output
    patch_client.push_base_images.assert_not_called()


def test_admin_infra_push_base_images_yes(patch_client):
    result = runner.invoke(app, ["admin", "infra", "push-base-images", "--yes"])
    assert result.exit_code == 0
    patch_client.push_base_images.assert_called_once()


def test_admin_infra_apply_k8s_policies_yes(patch_client):
    result = runner.invoke(app, ["admin", "infra", "apply-k8s-policies", "--yes"])
    assert result.exit_code == 0
    patch_client.apply_kubernetes_namespaces_policies.assert_called_once()


def test_admin_code_studio_template_list(patch_client):
    result = runner.invoke(app, ["admin", "code-studio-template", "list"])
    assert result.exit_code == 0
    assert "vscode" in result.output


def _wire_cst_template_settings(patch_client, blocks=None):
    """Helper: rig get_code_studio_template(...).get_settings() to return a
    mutable raw dict containing the given blocks. Returns (raw, settings)."""
    from unittest.mock import MagicMock

    if blocks is None:
        blocks = []
    raw = {
        "id": "GovernCopilot",
        "label": "Govern Copilot",
        "type": "block_based",
        "params": {"blocks": blocks},
    }
    settings = MagicMock()
    settings.get_raw.return_value = raw
    tpl = MagicMock()
    tpl.get_settings.return_value = settings
    patch_client.get_code_studio_template.return_value = tpl
    return raw, settings, tpl


def test_admin_cst_get_returns_raw_settings(patch_client):
    raw, _, _ = _wire_cst_template_settings(patch_client)
    result = runner.invoke(
        app,
        ["--format", "json", "admin", "code-studio-template", "get", "GovernCopilot"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["id"] == "GovernCopilot"
    assert data["params"]["blocks"] == raw["params"]["blocks"]


def test_admin_cst_list_blocks(patch_client):
    _wire_cst_template_settings(
        patch_client,
        blocks=[
            {"type": "dss_base_image", "params": {}},
            {"type": "append_dockerfile", "params": {"label": "Custom DF"}},
            {"type": "entrypoint", "params": {"label": "webapp"}},
        ],
    )
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "admin",
            "code-studio-template",
            "list-blocks",
            "GovernCopilot",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert [b["type"] for b in data] == [
        "dss_base_image",
        "append_dockerfile",
        "entrypoint",
    ]
    assert data[1]["label"] == "Custom DF"


def test_admin_cst_set_dockerfile_replaces_block(patch_client):
    raw, settings, _ = _wire_cst_template_settings(
        patch_client,
        blocks=[
            {
                "type": "append_dockerfile",
                "params": {"dockerfile": "OLD", "label": "DF"},
            },
        ],
    )
    result = runner.invoke(
        app,
        [
            "admin",
            "code-studio-template",
            "set-dockerfile-append",
            "GovernCopilot",
            "--dockerfile",
            "RUN echo hi",
        ],
    )
    assert result.exit_code == 0, result.output
    settings.save.assert_called_once()
    assert raw["params"]["blocks"][0]["params"]["dockerfile"] == "RUN echo hi"
    # Other params (label) preserved.
    assert raw["params"]["blocks"][0]["params"]["label"] == "DF"


def test_admin_cst_set_dockerfile_errors_when_no_block(patch_client):
    _wire_cst_template_settings(
        patch_client,
        blocks=[{"type": "dss_base_image", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "admin",
            "code-studio-template",
            "set-dockerfile-append",
            "GovernCopilot",
            "--dockerfile",
            "RUN echo hi",
        ],
    )
    assert result.exit_code != 0
    assert "no append_dockerfile block" in result.output


def test_admin_cst_add_block_appends(patch_client):
    raw, settings, _ = _wire_cst_template_settings(patch_client, blocks=[])
    result = runner.invoke(
        app,
        [
            "admin",
            "code-studio-template",
            "add-block",
            "GovernCopilot",
            "--type",
            "append_dockerfile",
            "--params",
            '{"dockerfile":"x"}',
        ],
    )
    assert result.exit_code == 0, result.output
    settings.save.assert_called_once()
    assert raw["params"]["blocks"] == [
        {"type": "append_dockerfile", "params": {"dockerfile": "x"}}
    ]


def test_admin_cst_remove_block_requires_yes(patch_client):
    _wire_cst_template_settings(
        patch_client,
        blocks=[{"type": "append_dockerfile", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "admin",
            "code-studio-template",
            "remove-block",
            "GovernCopilot",
            "--index",
            "0",
        ],
    )
    # Tier-2 DELETE blocks without --yes (exit 77).
    assert result.exit_code != 0


def test_admin_cst_remove_block_with_yes(patch_client):
    raw, _settings, _ = _wire_cst_template_settings(
        patch_client,
        blocks=[
            {"type": "dss_base_image", "params": {}},
            {"type": "append_dockerfile", "params": {}},
        ],
    )
    result = runner.invoke(
        app,
        [
            "admin",
            "code-studio-template",
            "remove-block",
            "GovernCopilot",
            "--index",
            "1",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw["params"]["blocks"] == [{"type": "dss_base_image", "params": {}}]


def test_admin_cst_remove_block_index_out_of_range(patch_client):
    _wire_cst_template_settings(
        patch_client,
        blocks=[{"type": "dss_base_image", "params": {}}],
    )
    result = runner.invoke(
        app,
        [
            "admin",
            "code-studio-template",
            "remove-block",
            "GovernCopilot",
            "--index",
            "99",
            "--yes",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output


def test_admin_cst_build_returns_job_id(patch_client):
    from unittest.mock import MagicMock

    fut = MagicMock()
    fut.job_id = "build-123"
    tpl = MagicMock()
    tpl.build.return_value = fut
    patch_client.get_code_studio_template.return_value = tpl

    result = runner.invoke(
        app, ["admin", "code-studio-template", "build", "GovernCopilot"]
    )
    assert result.exit_code == 0, result.output
    assert "build-123" in result.output
    tpl.build.assert_called_once_with(disable_docker_cache=False)


def test_admin_cst_set_block_params_merges(patch_client):
    """Default shallow-merge: set one key without clobbering the rest."""
    raw, settings, _ = _wire_cst_template_settings(
        patch_client,
        blocks=[
            {
                "type": "pycdstdioblk_replicate_app",
                "params": {"webapp_port": 5000, "label": "app"},
            },
        ],
    )
    result = runner.invoke(
        app,
        [
            "admin",
            "code-studio-template",
            "set-block-params",
            "GovernCopilot",
            "--index",
            "0",
            "--params",
            '{"llmmesh_model": "openai:gpt-4o"}',
        ],
    )
    assert result.exit_code == 0, result.output
    settings.save.assert_called_once()
    params = raw["params"]["blocks"][0]["params"]
    assert params["llmmesh_model"] == "openai:gpt-4o"
    assert params["webapp_port"] == 5000  # preserved by merge
    assert params["label"] == "app"  # preserved by merge


def test_admin_cst_set_block_params_replace(patch_client):
    """--replace overwrites the whole params object."""
    raw, _settings, _ = _wire_cst_template_settings(
        patch_client,
        blocks=[{"type": "pycdstdioblk_x_y", "params": {"webapp_port": 5000}}],
    )
    result = runner.invoke(
        app,
        [
            "admin",
            "code-studio-template",
            "set-block-params",
            "GovernCopilot",
            "--index",
            "0",
            "--params",
            '{"only": "this"}',
            "--replace",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw["params"]["blocks"][0]["params"] == {"only": "this"}


def test_admin_cst_set_block_params_bad_index(patch_client):
    _wire_cst_template_settings(patch_client, blocks=[{"type": "x", "params": {}}])
    result = runner.invoke(
        app,
        [
            "admin",
            "code-studio-template",
            "set-block-params",
            "GovernCopilot",
            "--index",
            "5",
            "--params",
            "{}",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output


def _wire_cst_build_future(patch_client, job_id, peek, full):
    """Rig get_code_studio_template(...).build() + the futures poll for a
    --wait run. `peek` is the first /futures peek body, `full` the result."""
    from unittest.mock import MagicMock

    fut = MagicMock()
    fut.job_id = job_id
    tpl = MagicMock()
    tpl.build.return_value = fut
    patch_client.get_code_studio_template.return_value = tpl
    patch_client._perform_json.side_effect = [peek, full]


def test_admin_cst_build_wait_success(patch_client):
    """The verdict reads result.messages (InfoMessages booleans), not the
    nonexistent top-level success/messages keys: no error/fatal → succeeded."""
    _wire_cst_build_future(
        patch_client,
        "FUT-1",
        peek={"alive": False},
        full={
            "hasResult": True,
            "result": {
                "messages": {
                    "error": False,
                    "fatal": False,
                    "messages": [{"severity": "INFO", "message": "Using cache"}],
                },
                "builds": [{"configName": "default"}],
            },
        },
    )
    result = runner.invoke(
        app, ["admin", "code-studio-template", "build", "tpl1", "--wait"]
    )
    assert result.exit_code == 0, result.output
    assert "succeeded" in result.output
    assert "FAILED" not in result.output


def test_admin_cst_build_wait_genuine_failure(patch_client):
    """result.messages.error=true is a real failure → exit 1 with the message."""
    _wire_cst_build_future(
        patch_client,
        "FUT-2",
        peek={"alive": False},
        full={
            "hasResult": True,
            "result": {
                "messages": {
                    "error": True,
                    "messages": [
                        {"severity": "ERROR", "message": "Dockerfile step failed"}
                    ],
                },
            },
        },
    )
    result = runner.invoke(
        app, ["admin", "code-studio-template", "build", "tpl1", "--wait"]
    )
    assert result.exit_code == 1, result.output
    assert "FAILED" in result.output
    assert "Dockerfile step failed" in result.output


def test_admin_cst_build_wait_genuine_failure_json_exits_nonzero(patch_client):
    """-o json must carry the same verdict in the exit code, not always 0."""
    _wire_cst_build_future(
        patch_client,
        "FUT-2J",
        peek={"alive": False},
        full={
            "hasResult": True,
            "result": {
                "messages": {
                    "error": True,
                    "messages": [
                        {"severity": "ERROR", "message": "Dockerfile step failed"}
                    ],
                },
            },
        },
    )
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "admin",
            "code-studio-template",
            "build",
            "tpl1",
            "--wait",
        ],
    )
    assert result.exit_code == 1, result.output
    assert "Dockerfile step failed" in result.output


def test_admin_cst_build_wait_no_result_is_ambiguous(patch_client):
    """hasResult=false (future GC'd before fetch — common on sub-second
    layer-cache builds) is ambiguous: warn + point at inspect-build, exit 0.
    Printing FAILED here is the known false-negative."""
    _wire_cst_build_future(
        patch_client,
        "FUT-3",
        peek={"alive": False},
        full={"hasResult": False},
    )
    result = runner.invoke(
        app, ["admin", "code-studio-template", "build", "tpl1", "--wait"]
    )
    assert result.exit_code == 0, result.output
    assert "inspect-build" in result.output
    assert "FAILED" not in result.output


# =============================================================================
# admin code-studio-template inspect-build — remote vs local docker probe
# =============================================================================


def test_admin_cst_inspect_build_remote_skips_local_docker(patch_client):
    """A non-localhost profile must SKIP the local docker probe and say so —
    the image was built on the remote node, not this machine."""
    _wire_cst_template_settings(patch_client, blocks=[])
    patch_client.host = "https://dss.acme.example.com"
    result = runner.invoke(
        app, ["admin", "code-studio-template", "inspect-build", "GovernCopilot"]
    )
    assert result.exit_code == 0, result.output
    assert "local docker check skipped" in result.output
    # Rich may wrap the message across lines; normalize whitespace before matching.
    assert "remote instance" in " ".join(result.output.split())
    # Must NOT claim a (misleading) local-docker miss.
    assert "not found via local docker" not in result.output


def test_admin_cst_inspect_build_remote_json(patch_client):
    """JSON output carries the same remote-skip relabel."""
    _wire_cst_template_settings(patch_client, blocks=[])
    patch_client.host = "https://dss.acme.example.com"
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "admin",
            "code-studio-template",
            "inspect-build",
            "GovernCopilot",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "local docker check skipped" in data["dockerImage"]


def test_admin_cst_inspect_build_localhost_probes_docker(patch_client, monkeypatch):
    """A localhost profile keeps the local docker probe; with no image found it
    reports the local miss (NOT the remote-skip relabel)."""
    _wire_cst_template_settings(patch_client, blocks=[])
    patch_client.host = "http://localhost:11200"
    # Force the docker probe to find nothing (docker missing on PATH).
    monkeypatch.setattr("shutil.which", lambda _name: None)
    result = runner.invoke(
        app, ["admin", "code-studio-template", "inspect-build", "GovernCopilot"]
    )
    assert result.exit_code == 0, result.output
    assert "not found via local docker" in result.output
    assert "local docker check skipped" not in result.output


# =============================================================================
# admin connection / code-env — top-level namespace redirect
# =============================================================================


def test_admin_connection_redirects(patch_client):
    """`dku admin connection list` is captured and redirected, not a bare
    'No such command'."""
    result = runner.invoke(app, ["admin", "connection", "list"])
    assert result.exit_code != 0
    assert "No such command" not in result.output
    assert "top-level group" in result.output
    assert "dku connection list" in result.output


def test_admin_code_env_redirects(patch_client):
    """`dku admin code-env list` is captured and redirected."""
    result = runner.invoke(app, ["admin", "code-env", "list"])
    assert result.exit_code != 0
    assert "No such command" not in result.output
    assert "top-level group" in result.output
    assert "dku code-env list" in result.output


def test_admin_connection_redirect_no_args(patch_client):
    """Bare `dku admin connection` still redirects with a sensible example."""
    result = runner.invoke(app, ["admin", "connection"])
    assert result.exit_code != 0
    assert "dku connection list" in result.output


# =============================================================================
# admin llm-cost
# =============================================================================


def test_admin_llm_cost_counters(patch_client):
    result = runner.invoke(app, ["admin", "llm-cost", "counters"])
    assert result.exit_code == 0
    assert "global-monthly" in result.output


def test_admin_llm_cost_counters_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "admin", "llm-cost", "counters"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["counters"][0]["id"] == "global-monthly"


def test_admin_llm_cost_get_missing(patch_client):
    result = runner.invoke(app, ["admin", "llm-cost", "get", "does-not-exist"])
    assert result.exit_code == 1
    assert "No counter" in result.output


def test_admin_llm_cost_get_found(patch_client):
    result = runner.invoke(app, ["admin", "llm-cost", "get", "global-monthly"])
    assert result.exit_code == 0
    assert "global-monthly" in result.output


# =============================================================================
# admin messaging delete / send-test
# =============================================================================


def test_admin_messaging_delete_blocks_without_confirm_name(patch_client):
    # Tier-3 cascade: --yes alone is not enough; needs --confirm-name <channel>.
    result = runner.invoke(app, ["admin", "messaging", "delete", "ops-smtp", "--yes"])
    assert result.exit_code == 77
    assert "BLOCKED" in result.output
    patch_client.get_messaging_channel.return_value.delete.assert_not_called()


def test_admin_messaging_delete_yes(patch_client):
    result = runner.invoke(
        app,
        [
            "admin",
            "messaging",
            "delete",
            "ops-smtp",
            "--yes",
            "--confirm-name",
            "ops-smtp",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_messaging_channel.return_value.delete.assert_called_once()


def test_admin_messaging_send_test(patch_client):
    result = runner.invoke(
        app,
        [
            "admin",
            "messaging",
            "send-test",
            "--id",
            "ops-smtp",
            "-P",
            "PROJ1",
            "--to",
            "alice@example.com,bob@example.com",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_messaging_channel.return_value.send.assert_called_once()


# =============================================================================
# admin disk-footprint
# =============================================================================


def test_admin_disk_footprint_global(patch_client):
    result = runner.invoke(app, ["admin", "disk-footprint", "global"])
    assert result.exit_code == 0
    assert "12345" in result.output


def test_admin_disk_footprint_project(patch_client):
    result = runner.invoke(app, ["admin", "disk-footprint", "project", "PROJ1"])
    assert result.exit_code == 0
    assert "PROJ1" in result.output
    patch_client.get_data_directories_footprint.return_value.compute_project_footprint.assert_called_once()


def test_admin_disk_footprint_all_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "admin", "disk-footprint", "all"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["size"] == 99999


def test_admin_disk_footprint_unknown(patch_client):
    result = runner.invoke(app, ["admin", "disk-footprint", "unknown"])
    assert result.exit_code == 0
    patch_client.get_data_directories_footprint.return_value.compute_unknown_footprint.assert_called_once()


# =============================================================================
# admin catalog-index
# =============================================================================


def test_admin_catalog_index_requires_target(patch_client):
    result = runner.invoke(app, ["admin", "catalog-index"])
    assert result.exit_code == 1
    assert "--all" in result.output


def test_admin_catalog_index_bad_mode(patch_client):
    result = runner.invoke(app, ["admin", "catalog-index", "--all", "--mode", "BOGUS"])
    assert result.exit_code == 1
    assert "FULL" in result.output


def test_admin_catalog_index_all(patch_client):
    result = runner.invoke(app, ["admin", "catalog-index", "--all"])
    assert result.exit_code == 0
    patch_client.catalog_index_connections.assert_called_once()
    _, kwargs = patch_client.catalog_index_connections.call_args
    assert kwargs["all_connections"] is True


def test_admin_catalog_index_named(patch_client):
    result = runner.invoke(app, ["admin", "catalog-index", "--connections", "snow,pg"])
    assert result.exit_code == 0
    _, kwargs = patch_client.catalog_index_connections.call_args
    assert kwargs["connection_names"] == ["snow", "pg"]


# =============================================================================
# admin assets
# =============================================================================


def test_admin_assets_list_collections(patch_client):
    result = runner.invoke(app, ["admin", "assets", "list-collections"])
    assert result.exit_code == 0
    assert "Canonical" in result.output


def test_admin_assets_list_prompts(patch_client):
    result = runner.invoke(app, ["admin", "assets", "list-prompts"])
    assert result.exit_code == 0
    assert "summarise" in result.output


def test_admin_assets_list_prompts_filtered(patch_client):
    result = runner.invoke(
        app, ["admin", "assets", "list-prompts", "--collections", "col-1"]
    )
    assert result.exit_code == 0
    _, kwargs = (
        patch_client.get_enterprise_asset_library.return_value.list_prompts.call_args
    )
    assert kwargs["restrict_collections"] == ["col-1"]


# =============================================================================
# admin audit-log
# =============================================================================


def test_admin_audit_log_basic(patch_client):
    result = runner.invoke(app, ["admin", "audit-log", "--type", "migration.start"])
    assert result.exit_code == 0
    patch_client.log_custom_audit.assert_called_once()


def test_admin_audit_log_with_params(patch_client):
    result = runner.invoke(
        app,
        [
            "admin",
            "audit-log",
            "--type",
            "deploy",
            "--params",
            '{"branch":"main","sha":"abc"}',
        ],
    )
    assert result.exit_code == 0
    _, kwargs = patch_client.log_custom_audit.call_args
    assert kwargs["custom_params"] == {"branch": "main", "sha": "abc"}


def test_admin_audit_log_bad_params(patch_client):
    result = runner.invoke(
        app, ["admin", "audit-log", "--type", "deploy", "--params", '"not-an-object"']
    )
    assert result.exit_code == 1
    assert "JSON object" in result.output
