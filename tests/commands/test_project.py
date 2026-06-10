"""Tests for project commands."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_project_list_table(patch_client):
    result = runner.invoke(app, ["project", "list"])
    assert result.exit_code == 0
    assert "PROJ1" in result.output or "Project One" in result.output


def test_project_list_json(patch_client):
    result = runner.invoke(app, ["project", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["key"] == "PROJ1"


def test_project_list_uses_single_call_not_n_plus_1(patch_client):
    """list must use one list_projects() call, not a per-project get_metadata()
    loop (the N+1 that made it ~25s on busy instances)."""
    result = runner.invoke(app, ["project", "list", "-o", "json"])
    assert result.exit_code == 0, result.output
    patch_client.list_projects.assert_called_once()
    patch_client.get_project.assert_not_called()
    parsed = json.loads(result.output)
    assert parsed[1] == {"key": "PROJ2", "name": "Project Two", "short_desc": ""}


def test_project_get(patch_client):
    result = runner.invoke(app, ["project", "get", "PROJ1"])
    assert result.exit_code == 0


def test_project_get_json(patch_client):
    """JSON returns the canonical project dict (metadata + key + counts), not
    a re-shaped {field, value} list."""
    result = runner.invoke(app, ["project", "get", "PROJ1", "-o", "json"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed, dict)
    # Canonical metadata keys preserved
    assert parsed["key"] == "PROJ1"
    assert parsed["label"] == "Project One"
    assert parsed["shortDesc"] == "First project"


def test_project_get_shows_counts(patch_client):
    """Counts come back as a typed `counts` sub-dict in JSON output."""
    result = runner.invoke(app, ["project", "get", "PROJ1", "-o", "json"])
    parsed = json.loads(result.output)
    assert parsed["counts"] == {
        "datasets": 1,
        "recipes": 1,
        "scenarios": 1,
    }


def test_project_get_text_keeps_field_value_layout(patch_client):
    """Default text output preserves the human Field/Value summary."""
    result = runner.invoke(app, ["project", "get", "PROJ1"])
    assert result.exit_code == 0
    # Smoke-check the human layout — labels and values appear
    assert "Key" in result.output
    assert "PROJ1" in result.output
    assert "Project One" in result.output
    assert "Datasets" in result.output


def test_project_list_uses_config_default_output(patch_client):
    with patch("dku_cli.config.get_default_output", return_value="json"):
        result = runner.invoke(app, ["project", "list"])

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["key"] == "PROJ1"


def test_project_list_rejects_invalid_output(patch_client):
    result = runner.invoke(app, ["project", "list", "-o", "yaml"])
    assert result.exit_code != 0
    assert "Output format must be one of" in result.output


# --- project create ---


def test_project_create_table(patch_client):
    result = runner.invoke(
        app, ["project", "create", "NEW_PROJ", "--name", "New Project"]
    )
    assert result.exit_code == 0
    assert "NEW_PROJ" in result.output
    patch_client.create_project.assert_called_once_with(
        "NEW_PROJ", "New Project", "testuser", description=""
    )


def test_project_create_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--quiet",
            "project",
            "create",
            "NEW_PROJ",
            "--name",
            "New Project",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert any(d["field"] == "Key" and d["value"] == "NEW_PROJ" for d in parsed)
    assert any(d["field"] == "Owner" and d["value"] == "testuser" for d in parsed)


def test_project_create_with_description(patch_client):
    result = runner.invoke(
        app,
        ["project", "create", "NEW_PROJ", "--name", "New", "--description", "A desc"],
    )
    assert result.exit_code == 0
    patch_client.create_project.assert_called_once_with(
        "NEW_PROJ", "New", "testuser", description="A desc"
    )


# --- project create --if-not-exists ---


def test_project_create_if_not_exists_when_exists(patch_client):
    """--if-not-exists silently succeeds when project already exists."""
    patch_client.create_project.side_effect = Exception(
        "Project 'NEW_PROJ' already exists"
    )
    result = runner.invoke(
        app,
        ["project", "create", "NEW_PROJ", "--name", "New", "--if-not-exists"],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output.lower()


def test_project_create_if_not_exists_when_new(patch_client):
    """--if-not-exists creates normally when project doesn't exist."""
    result = runner.invoke(
        app,
        ["project", "create", "NEW_PROJ", "--name", "New", "--if-not-exists"],
    )
    assert result.exit_code == 0
    patch_client.create_project.assert_called_once()


def test_project_create_without_if_not_exists_still_fails(patch_client):
    """Without --if-not-exists, already-exists error propagates normally."""
    patch_client.create_project.side_effect = Exception(
        "Project 'NEW_PROJ' already exists"
    )
    result = runner.invoke(
        app,
        ["project", "create", "NEW_PROJ", "--name", "New"],
    )
    assert result.exit_code != 0


def test_project_create_already_exists_shows_hint(patch_client):
    """Already-exists error without --if-not-exists shows actionable hints."""
    patch_client.create_project.side_effect = Exception(
        "Project 'PROJ1' already exists"
    )
    result = runner.invoke(
        app,
        ["project", "create", "PROJ1", "--name", "Test"],
    )
    assert result.exit_code != 0
    assert "--if-not-exists" in result.output
    assert "--yes" in result.output


# --- project set-metadata ---


def test_project_set_metadata_name(patch_client):
    result = runner.invoke(
        app, ["project", "set-metadata", "PROJ1", "--name", "New Name"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.set_metadata.call_args[0][0]
    assert call_args["label"] == "New Name"


def test_project_set_metadata_description(patch_client):
    result = runner.invoke(
        app, ["project", "set-metadata", "PROJ1", "--description", "A new desc"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.set_metadata.call_args[0][0]
    # Both fields are written; some DSS versions read 'description', others
    # 'shortDesc' — covers either at the cost of one extra key (PENDING.md
    # 2026-05-11).
    assert call_args["shortDesc"] == "A new desc"
    assert call_args["description"] == "A new desc"


def test_project_set_metadata_detects_silent_no_op(patch_client):
    """If DSS accepts the PUT but doesn't actually persist the description,
    the round-trip GET will show the old value. The CLI must warn AND exit
    non-zero so chained scripts don't drift on stale state."""
    proj = patch_client.get_project("PROJ1")
    # Simulate the DSS endpoint silently dropping the description field:
    # both get_metadata calls return a fresh dict with the OLD description,
    # regardless of what set_metadata received.
    proj.set_metadata.side_effect = None
    proj.get_metadata.side_effect = lambda: {
        "label": "Project One",
        "shortDesc": "stuck old",
        "description": "stuck old",
    }
    result = runner.invoke(
        app, ["project", "set-metadata", "PROJ1", "--description", "should land"]
    )
    assert result.exit_code == 1
    # Rich line-wraps long warn lines in the runner's narrow buffer; use a
    # phrase that survives the wrap and the stuck-old leak.
    assert "stuck old" in result.output
    assert "set-metadata reported success" in result.output


def test_project_set_metadata_both(patch_client):
    result = runner.invoke(
        app,
        [
            "project",
            "set-metadata",
            "PROJ1",
            "--name",
            "Better Name",
            "--description",
            "Better desc",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.set_metadata.call_args[0][0]
    assert call_args["label"] == "Better Name"
    assert call_args["shortDesc"] == "Better desc"


def test_project_set_metadata_no_args(patch_client):
    result = runner.invoke(app, ["project", "set-metadata", "PROJ1"])
    assert result.exit_code != 0


# --- project delete ---


def test_project_delete_without_yes_blocks(patch_client):
    result = runner.invoke(app, ["project", "delete", "PROJ1"])
    assert result.exit_code == 77


def test_project_delete_without_confirm_name_blocks(patch_client):
    """Tier-3 needs both --yes and --confirm-name matching the project key."""
    result = runner.invoke(app, ["project", "delete", "PROJ1", "--yes"])
    assert result.exit_code == 77


def test_project_delete_with_wrong_confirm_name_blocks(patch_client):
    result = runner.invoke(
        app,
        ["project", "delete", "PROJ1", "--yes", "--confirm-name", "WRONG_PROJ"],
    )
    assert result.exit_code == 77


def test_project_delete_with_matching_confirm_name(patch_client):
    result = runner.invoke(
        app,
        ["project", "delete", "PROJ1", "--yes", "--confirm-name", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.delete.assert_called_once_with(
        clear_managed_datasets=False,
        clear_output_managed_folders=False,
    )
    assert "--drop-data" in result.output


def test_project_delete_with_drop_data(patch_client):
    result = runner.invoke(
        app,
        [
            "project",
            "delete",
            "PROJ1",
            "--yes",
            "--confirm-name",
            "PROJ1",
            "--drop-data",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.delete.assert_called_once_with(
        clear_managed_datasets=True,
        clear_output_managed_folders=True,
    )
    assert "Re-run with --drop-data" not in result.output


def test_project_delete_with_clear_managed_alias(patch_client):
    """--clear-managed is an alias for --drop-data."""
    result = runner.invoke(
        app,
        [
            "project",
            "delete",
            "PROJ1",
            "--yes",
            "--confirm-name",
            "PROJ1",
            "--clear-managed",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.delete.assert_called_once_with(
        clear_managed_datasets=True,
        clear_output_managed_folders=True,
    )


def test_project_delete_dangerous_still_needs_confirm_name(patch_client, monkeypatch):
    """--dangerous / DKU_DANGEROUS does NOT bypass tier-3 --confirm-name."""
    monkeypatch.setenv("DKU_DANGEROUS", "1")
    result = runner.invoke(app, ["project", "delete", "PROJ1", "--yes"])
    assert result.exit_code == 77


# --- project duplicate ---


def test_project_duplicate(patch_client):
    result = runner.invoke(
        app,
        [
            "project",
            "duplicate",
            "PROJ1",
            "--target-key",
            "PROJ_COPY",
            "--target-name",
            "Project Copy",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.duplicate.assert_called_once_with(
        target_project_key="PROJ_COPY", target_project_name="Project Copy"
    )


def test_project_duplicate_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--quiet",
            "project",
            "duplicate",
            "PROJ1",
            "--target-key",
            "PROJ_COPY",
            "--target-name",
            "Project Copy",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert any(d["field"] == "Source" and d["value"] == "PROJ1" for d in parsed)
    assert any(d["field"] == "Target Key" and d["value"] == "PROJ_COPY" for d in parsed)


# --- project variables ---


def test_project_variables(patch_client):
    result = runner.invoke(
        app, ["project", "variables", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["standard"]["key1"] == "val1"
    assert parsed["local"]["local1"] == "lval1"


# --- project set-variables ---


def test_project_set_variables_with_set(patch_client):
    result = runner.invoke(
        app,
        ["project", "set-variables", "--project", "PROJ1", "--set", "new_key=new_val"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    # Should have called set_variables with the merged dict
    call_args = proj.set_variables.call_args[0][0]
    assert call_args["standard"]["new_key"] == "new_val"
    assert call_args["standard"]["key1"] == "val1"  # existing preserved


def test_project_set_variables_with_definition_blocks_without_yes(patch_client):
    new_vars = json.dumps({"standard": {"x": "1"}, "local": {}})
    result = runner.invoke(
        app,
        ["project", "set-variables", "--project", "PROJ1", "--definition", new_vars],
    )
    assert result.exit_code == 77


def test_project_set_variables_with_definition(patch_client):
    new_vars = json.dumps({"standard": {"x": "1"}, "local": {}})
    result = runner.invoke(
        app,
        [
            "project",
            "set-variables",
            "--project",
            "PROJ1",
            "--definition",
            new_vars,
            "--yes",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.set_variables.call_args[0][0]
    assert call_args == {"standard": {"x": "1"}, "local": {}}


def test_project_set_variables_no_args(patch_client):
    result = runner.invoke(app, ["project", "set-variables", "--project", "PROJ1"])
    assert result.exit_code != 0


# --- project permissions ---


def test_project_permissions(patch_client):
    result = runner.invoke(
        app, ["project", "permissions", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["permissions"][0]["user"] == "admin"


# --- project set-permissions ---


def test_project_set_permissions_blocks_without_yes(patch_client):
    perms = json.dumps({"permissions": [{"user": "new_user", "admin": False}]})
    result = runner.invoke(
        app,
        ["project", "set-permissions", "--project", "PROJ1", "--definition", perms],
    )
    assert result.exit_code == 77


def test_project_set_permissions(patch_client):
    perms = json.dumps({"permissions": [{"user": "new_user", "admin": False}]})
    result = runner.invoke(
        app,
        [
            "project",
            "set-permissions",
            "--project",
            "PROJ1",
            "--definition",
            perms,
            "--yes",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.set_permissions.call_args[0][0]
    assert call_args["permissions"][0]["user"] == "new_user"


# --- project tags ---


def test_project_tags(patch_client):
    result = runner.invoke(app, ["project", "tags", "--project", "PROJ1"])
    assert result.exit_code == 0
    # Default metadata mock doesn't have tags, so should return empty list
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)


def test_project_tags_positional(patch_client):
    result = runner.invoke(app, ["project", "tags", "PROJ1", "-o", "json"])
    assert result.exit_code == 0


# --- project inspect ---


def test_project_inspect_json(patch_client):
    result = runner.invoke(app, ["project", "inspect", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["key"] == "PROJ1"
    assert parsed["name"] == "Project One"
    assert "datasets" in parsed
    assert "recipes" in parsed
    assert "scenarios" in parsed
    assert "counts" in parsed


def test_project_inspect_table(patch_client):
    result = runner.invoke(app, ["project", "inspect", "PROJ1"])
    assert result.exit_code == 0
    assert "Project Inspect" in result.output


def test_project_inspect_with_flag(patch_client):
    result = runner.invoke(app, ["project", "inspect", "-P", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["key"] == "PROJ1"


# --- unknown / inaccessible project is NOT an auth error ---
#
# DSS returns 401/Unauthorized — never 404 — for a project that doesn't exist OR
# that the caller can't access, and refuses to reveal which. The CLI must
# prescribe key-vs-name instead of "check your API key", or agents waste turns
# re-authenticating a valid key (a real benchmark failure cost 6 steps). The
# trigger below — passing the display NAME "AdvisorGPT" instead of the KEY — is
# exactly how the live failure was reproduced.

_DSS_PROJECT_401 = (
    "com.dataiku.dip.exceptions.UnauthorizedException: "
    "Failed to read project permissions"
)


def test_project_inspect_unknown_project_is_not_auth_error(patch_client):
    from dataikuapi.utils import DataikuException

    proj = patch_client.get_project.return_value
    proj.get_metadata.side_effect = DataikuException(_DSS_PROJECT_401)

    result = runner.invoke(app, ["project", "inspect", "AdvisorGPT"])
    assert result.exit_code == 3, result.stderr
    err = result.stderr
    assert "check your API key" not in err
    # Must NOT prescribe the generic re-auth fix ("Run 'dku auth login'"),
    # and MUST carry the explicit "your key is fine, do not re-auth" warning.
    assert "Run 'dku auth login'" not in err
    assert "Do NOT run" in err
    assert "AdvisorGPT" in err
    assert "dku project list" in err
    assert "KEY" in err and "NAME" in err


def test_project_inspect_unknown_project_json_error(patch_client):
    from dataikuapi.utils import DataikuException

    proj = patch_client.get_project.return_value
    proj.get_metadata.side_effect = DataikuException(_DSS_PROJECT_401)

    result = runner.invoke(
        app, ["--errors", "json", "project", "inspect", "AdvisorGPT"]
    )
    assert result.exit_code == 3
    assert result.stdout == ""
    parsed = json.loads(result.stderr)
    assert parsed["error"]["code"] == "project_not_found"
    assert parsed["error"]["exit_code"] == 3
    assert "AdvisorGPT" in parsed["error"]["message"]
    # The misleading classification must be gone.
    assert parsed["error"]["code"] != "auth_error"


def test_project_get_unknown_project_is_not_auth_error(patch_client):
    """`project get` threads the key too, so it gets the same guidance."""
    from dataikuapi.utils import DataikuException

    proj = patch_client.get_project.return_value
    proj.get_metadata.side_effect = DataikuException(_DSS_PROJECT_401)

    result = runner.invoke(app, ["project", "get", "AdvisorGPT"])
    assert result.exit_code == 3
    assert "check your API key" not in result.stderr
    assert "AdvisorGPT" in result.stderr


def test_project_variables_unknown_project_is_not_auth_error(patch_client):
    """A -P-style command (key in --project, not positional) benefits as well."""
    from dataikuapi.utils import DataikuException

    proj = patch_client.get_project.return_value
    proj.get_variables.side_effect = DataikuException(_DSS_PROJECT_401)

    result = runner.invoke(
        app, ["project", "variables", "-P", "AdvisorGPT", "-o", "json"]
    )
    assert result.exit_code == 3
    assert "check your API key" not in result.stderr
    assert "AdvisorGPT" in result.stderr


# --- positional project key ---


def test_project_variables_positional(patch_client):
    result = runner.invoke(app, ["project", "variables", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["standard"]["key1"] == "val1"


def test_project_permissions_positional(patch_client):
    result = runner.invoke(app, ["project", "permissions", "PROJ1", "-o", "json"])
    assert result.exit_code == 0


def test_project_tags_with_tags(patch_client):
    # Patch metadata to include tags
    proj = patch_client.get_project("PROJ1")
    proj.get_metadata.return_value = {
        "label": "Project One",
        "shortDesc": "First project",
        "tags": ["production", "ml"],
    }
    result = runner.invoke(app, ["project", "tags", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "production" in parsed
    assert "ml" in parsed


# --- ai-describe ---


def test_project_ai_describe(patch_client):
    result = runner.invoke(app, ["project", "ai-describe", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "customer data pipelines" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.generate_ai_description.assert_called_once_with(
        language="english", purpose="generic", length="medium", save_description=False
    )


def test_project_ai_describe_save(patch_client):
    result = runner.invoke(
        app, ["project", "ai-describe", "--save", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "saved" in result.output.lower()
    proj = patch_client.get_project("PROJ1")
    proj.generate_ai_description.assert_called_once_with(
        language="english", purpose="generic", length="medium", save_description=True
    )


def test_project_ai_describe_json(patch_client):
    result = runner.invoke(
        app, ["project", "ai-describe", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "msg" in parsed
    assert "customer data pipelines" in parsed["msg"]


def test_project_ai_describe_custom_options(patch_client):
    result = runner.invoke(
        app,
        [
            "project",
            "ai-describe",
            "--language",
            "french",
            "--purpose",
            "technical",
            "--length",
            "high",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.generate_ai_description.assert_called_once_with(
        language="french", purpose="technical", length="high", save_description=False
    )


# --- project export ---


def test_project_export_no_flags_settings_only(patch_client, tmp_path):
    """No data flags => call export_to_file() with NO options= (preserves the
    original settings-only behavior)."""
    result = runner.invoke(
        app,
        ["project", "export", "PROJ1", "--dest", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    proj.export_to_file.assert_called_once()
    args, kwargs = proj.export_to_file.call_args
    # Positional path only; no options keyword passed.
    assert "options" not in kwargs
    assert args[0].endswith("PROJ1.zip")


def test_project_export_with_data_builds_options(patch_client, tmp_path):
    """--with-data turns on uploads + managed-FS + all datasets."""
    result = runner.invoke(
        app,
        ["project", "export", "PROJ1", "--with-data", "--dest", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    _, kwargs = proj.export_to_file.call_args
    opts = kwargs["options"]
    assert opts["exportUploads"] is True
    assert opts["exportManagedFS"] is True
    assert opts["exportAllDatasets"] is True
    # Granular-only keys not set by --with-data
    assert "exportManagedFolders" not in opts
    assert "exportInsightsData" not in opts


def test_project_export_granular_flags(patch_client, tmp_path):
    """Granular flags map to their individual option keys."""
    result = runner.invoke(
        app,
        [
            "project",
            "export",
            "PROJ1",
            "--managed-folders",
            "--insights-data",
            "--all-input-datasets",
            "--dest",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    _, kwargs = proj.export_to_file.call_args
    opts = kwargs["options"]
    assert opts == {
        "exportManagedFolders": True,
        "exportInsightsData": True,
        "exportAllInputDatasets": True,
    }


# --- project import ---


def test_project_import_happy_path(patch_client, tmp_path):
    archive = tmp_path / "PROJ1.zip"
    archive.write_bytes(b"PK\x03\x04 fake zip")
    handle = patch_client.prepare_project_import.return_value
    handle.execute.return_value = {"success": True, "targetProjectKey": "PROJ1"}

    result = runner.invoke(
        app,
        ["project", "import", str(archive), "--as", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    assert "PROJ1" in result.output
    # targetProjectKey carried into settings
    _, kwargs = handle.execute.call_args
    assert kwargs["settings"]["targetProjectKey"] == "PROJ1"


def test_project_import_remap_connection_shape(patch_client, tmp_path):
    archive = tmp_path / "PROJ1.zip"
    archive.write_bytes(b"PK\x03\x04 fake zip")
    handle = patch_client.prepare_project_import.return_value
    handle.execute.return_value = {"success": True, "targetProjectKey": "PROJ1"}

    result = runner.invoke(
        app,
        [
            "project",
            "import",
            str(archive),
            "--remap-connection",
            "pg_old=pg_new",
        ],
    )
    assert result.exit_code == 0, result.output
    _, kwargs = handle.execute.call_args
    assert kwargs["settings"]["remapping"] == {
        "connections": [{"source": "pg_old", "target": "pg_new"}]
    }


def test_project_import_failure_is_prescriptive(patch_client, tmp_path):
    """success=false must exit non-zero with prescriptive remap/create guidance."""
    archive = tmp_path / "PROJ1.zip"
    archive.write_bytes(b"PK\x03\x04 fake zip")
    handle = patch_client.prepare_project_import.return_value
    handle.execute.return_value = {
        "success": False,
        "messages": [{"message": "Connection 'pg_old' does not exist"}],
    }

    result = runner.invoke(
        app,
        ["project", "import", str(archive)],
    )
    assert result.exit_code != 0
    assert "pg_old" in result.output
    assert "--remap-connection" in result.output
    assert "dku connection create" in result.output


def test_project_import_missing_archive(patch_client, tmp_path):
    missing = tmp_path / "nope.zip"
    result = runner.invoke(app, ["project", "import", str(missing)])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    assert "dku project export" in result.output


def test_project_import_bad_remap_value(patch_client, tmp_path):
    archive = tmp_path / "PROJ1.zip"
    archive.write_bytes(b"PK\x03\x04 fake zip")
    result = runner.invoke(
        app,
        ["project", "import", str(archive), "--remap-connection", "noequals"],
    )
    assert result.exit_code != 0
    assert "SRC=TGT" in result.output


# --- timeline ---


def test_project_timeline_table(patch_client):
    result = runner.invoke(app, ["project", "timeline", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "admin" in result.output
    assert "dataiku" in result.output


def test_project_timeline_json(patch_client):
    result = runner.invoke(
        app, ["project", "timeline", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["createdBy"]["login"] == "admin"
    assert len(parsed["allContributors"]) == 2
    assert len(parsed["items"]) == 1


def test_project_timeline_custom_limit(patch_client):
    result = runner.invoke(
        app,
        ["project", "timeline", "--limit", "5", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.get_timeline.assert_called_once_with(item_count=5)
