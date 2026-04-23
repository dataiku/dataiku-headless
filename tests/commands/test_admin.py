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
    result = runner.invoke(app, ["admin", "logs", "-o", "json"])
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
    result = runner.invoke(app, ["admin", "usage", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["projects"] == 10
    assert parsed["datasets"] == 50


def test_admin_instance_info(patch_client):
    result = runner.invoke(app, ["admin", "instance-info"])
    assert result.exit_code == 0
    assert "DESIGN" in result.output


def test_admin_instance_info_json(patch_client):
    result = runner.invoke(app, ["admin", "instance-info", "-o", "json"])
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


def test_admin_license_upload_requires_yes(patch_client, tmp_path):
    f = tmp_path / "license.json"
    f.write_text('{"edition":"ENTERPRISE"}')
    result = runner.invoke(app, ["admin", "license", "upload", str(f)])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    # Confirm SDK was NOT called
    patch_client.set_license.assert_not_called()


def test_admin_license_upload_with_yes(patch_client, tmp_path):
    f = tmp_path / "license.json"
    f.write_text('{"edition":"ENTERPRISE"}')
    result = runner.invoke(app, ["admin", "license", "upload", str(f), "--yes"])
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


def test_admin_sso_set_dry_run(patch_client):
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
    assert result.exit_code == 0
    assert "Dry run" in result.output
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
            "--i-understand-lockout-risk",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_sso_settings.return_value.save.assert_called_once()


def test_admin_ldap_get(patch_client):
    result = runner.invoke(app, ["admin", "ldap", "get"])
    assert result.exit_code == 0
    assert "ldap.example.com" in result.output


def test_admin_azure_ad_get(patch_client):
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


def test_admin_settings_set_requires_yes(patch_client):
    payload = (
        '{"dssVersion":"14.0.2","impersonation":{"rules":[]},"containerSettings":{}}'
    )
    result = runner.invoke(app, ["admin", "settings", "set", "-d", payload])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    patch_client.get_general_settings.return_value.save.assert_not_called()


def test_admin_settings_set_rejects_partial_payload(patch_client):
    # Missing 'containerSettings' and 'impersonation'
    partial = '{"dssVersion":"14.0.2"}'
    result = runner.invoke(app, ["admin", "settings", "set", "-d", partial, "--yes"])
    assert result.exit_code == 1
    assert "missing" in result.output.lower()
    patch_client.get_general_settings.return_value.save.assert_not_called()


def test_admin_settings_set_applied(patch_client):
    full = '{"dssVersion":"14.0.2","impersonation":{"rules":[]},"containerSettings":{}}'
    result = runner.invoke(app, ["admin", "settings", "set", "-d", full, "--yes"])
    assert result.exit_code == 0
    patch_client.get_general_settings.return_value.save.assert_called_once()


# =============================================================================
# admin users-sync
# =============================================================================


def test_admin_users_sync_resync_all_requires_yes(patch_client):
    result = runner.invoke(app, ["admin", "users-sync", "resync-all"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    patch_client.start_resync_all_users_from_supplier.assert_not_called()


def test_admin_users_sync_resync_all_yes(patch_client):
    result = runner.invoke(app, ["admin", "users-sync", "resync-all", "--yes"])
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
    assert result.exit_code == 0
    assert "Dry run" in result.output
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
    assert result.exit_code == 0
    assert "Dry run" in result.output
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


# =============================================================================
# admin llm-cost
# =============================================================================


def test_admin_llm_cost_counters(patch_client):
    result = runner.invoke(app, ["admin", "llm-cost", "counters"])
    assert result.exit_code == 0
    assert "global-monthly" in result.output


def test_admin_llm_cost_counters_json(patch_client):
    result = runner.invoke(app, ["admin", "llm-cost", "counters", "-o", "json"])
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


def test_admin_messaging_delete_requires_yes(patch_client):
    result = runner.invoke(app, ["admin", "messaging", "delete", "ops-smtp"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    patch_client.get_messaging_channel.return_value.delete.assert_not_called()


def test_admin_messaging_delete_yes(patch_client):
    result = runner.invoke(app, ["admin", "messaging", "delete", "ops-smtp", "--yes"])
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
    result = runner.invoke(app, ["admin", "disk-footprint", "all", "-o", "json"])
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
