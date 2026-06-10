"""Tests for dku govern-blueprint commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def MagicMock_wrapper(raw: dict) -> MagicMock:
    """Build a MagicMock whose `.get_raw()` returns the given dict."""
    m = MagicMock()
    m.get_raw.return_value = raw
    return m


def test_blueprint_list(patch_client):
    result = runner.invoke(app, ["govern", "blueprint", "list"])
    assert result.exit_code == 0
    assert "govern_project" in result.output


def test_blueprint_list_json(patch_client):
    result = runner.invoke(app, ["govern", "blueprint", "list", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "bp.system.govern_project"


def test_blueprint_get(patch_client):
    result = runner.invoke(
        app, ["govern", "blueprint", "get", "bp.system.govern_project"]
    )
    assert result.exit_code == 0
    assert "govern_project" in result.output


def test_blueprint_get_json(patch_client):
    result = runner.invoke(
        app, ["govern", "blueprint", "get", "bp.system.govern_project", "-o", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "bp.system.govern_project"


def test_blueprint_list_versions(patch_client):
    result = runner.invoke(
        app, ["govern", "blueprint", "list-versions", "bp.system.govern_project"]
    )
    assert result.exit_code == 0
    assert "ACTIVE" in result.output or "Default" in result.output


def test_blueprint_list_versions_json(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "list-versions",
            "bp.system.govern_project",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["version_id"] == "bv.system.default"
    # JSON must carry BOTH the flat snake_case keys and the nested camelCase
    # `id` shape returned by get-version, so resolver code that does
    # `(v.get("id") or {}).get("versionId")` works against either endpoint.
    assert data[0]["id"]["versionId"] == "bv.system.default"
    assert data[0]["id"]["blueprintId"]
    assert data[0]["blueprint_id"] == data[0]["id"]["blueprintId"]


def test_blueprint_get_version(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "get-version",
            "bp.system.govern_project",
            "bv.system.default",
        ],
    )
    assert result.exit_code == 0
    assert "govern_project" in result.output or "Default" in result.output


def test_blueprint_get_version_json(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "get-version",
            "bp.system.govern_project",
            "bv.system.default",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["name"] == "Default"


def test_blueprint_fields(patch_client):
    """Test fields command shows field schema."""
    result = runner.invoke(
        app, ["govern", "blueprint", "fields", "bp.system.govern_project"]
    )
    assert result.exit_code == 0
    assert "description" in result.output
    assert "TEXT" in result.output
    assert "cost_rating" in result.output
    assert "CATEGORY" in result.output


def test_blueprint_fields_json(patch_client):
    """Test fields command in JSON output."""
    result = runner.invoke(
        app,
        ["govern", "blueprint", "fields", "bp.system.govern_project", "-o", "json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    field_ids = [f["field"] for f in data]
    assert "description" in field_ids
    assert "cost_rating" in field_ids
    # COMPUTE fields should be excluded
    assert "govern_models" not in field_ids


def test_blueprint_fields_shows_list_marker(patch_client):
    """Test that list fields are marked with * in the LIST column."""
    result = runner.invoke(
        app,
        ["govern", "blueprint", "fields", "bp.system.govern_project", "-o", "json"],
    )
    data = json.loads(result.output)
    countries = next(f for f in data if f["field"] == "countries")
    assert countries["list"] == "*"
    description = next(f for f in data if f["field"] == "description")
    assert description["list"] == ""


def test_blueprint_fields_shows_categories(patch_client):
    """Test that category values are shown."""
    result = runner.invoke(
        app,
        ["govern", "blueprint", "fields", "bp.system.govern_project", "-o", "json"],
    )
    data = json.loads(result.output)
    cost = next(f for f in data if f["field"] == "cost_rating")
    assert "Low" in cost["values"]
    assert "High" in cost["values"]


def test_blueprint_fields_shows_allowed_refs(patch_client):
    """Test that REFERENCE fields show allowed blueprints."""
    result = runner.invoke(
        app,
        ["govern", "blueprint", "fields", "bp.system.govern_project", "-o", "json"],
    )
    data = json.loads(result.output)
    bi = next(f for f in data if f["field"] == "business_initiative")
    assert "bp.system.business_initiative" in bi["values"]


# ---------------------------------------------------------------------------
# Version designer: create-version, set-version-definition, delete-version,
# version-status, set-version-status
# ---------------------------------------------------------------------------


def test_blueprint_create_strips_bp_prefix(patch_client):
    """`govern blueprint create bp.swag` should strip the prefix and pass
    'swag' to designer.create_blueprint — the API rejects the bp.<id> form
    on this endpoint while every other verb requires it."""
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "create",
            "bp.swag",
            "--definition",
            '{"name":"SWAG"}',
        ],
    )
    assert result.exit_code == 0, result.output
    designer.create_blueprint.assert_called_once_with("swag", {"name": "SWAG"})
    assert "Stripping 'bp.' prefix" in result.output


def test_blueprint_create_accepts_bare_identifier(patch_client):
    """Bare identifier passes straight through (no warning, no strip)."""
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "create",
            "swag",
            "--definition",
            '{"name":"SWAG"}',
        ],
    )
    assert result.exit_code == 0, result.output
    designer.create_blueprint.assert_called_once_with("swag", {"name": "SWAG"})
    assert "Stripping" not in result.output


def test_create_version_forwards_args(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "create-version",
            "bp.custom.my_bp",
            "v1",
            "--name",
            "Version 1",
            "--from",
            "bv.system.default",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Created version 'bv.v1'" in result.output
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    admin_bp.create_version.assert_called_once_with(
        "v1", name="Version 1", origin_version_id="bv.system.default"
    )


def test_create_version_minimal(patch_client):
    result = runner.invoke(
        app,
        ["govern", "blueprint", "create-version", "bp.custom.my_bp", "v1"],
    )
    assert result.exit_code == 0, result.output
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    admin_bp.create_version.assert_called_with("v1", name=None, origin_version_id=None)


def test_set_version_definition_saves_with_force(patch_client, tmp_path):
    payload = {
        "id": {"blueprintId": "bp.custom.my_bp", "versionId": "bv.system.default"},
        "name": "Default",
        "fieldDefinitions": {},
        "workflowDefinition": {"stepDefinitions": []},
        "logicalHookList": [],
        "actions": {},
        "uiDefinition": {"views": {}, "uiStepDefinitions": {}},
    }
    f = tmp_path / "bv.json"
    f.write_text(json.dumps(payload))
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-version-definition",
            "bp.custom.my_bp",
            "bv.system.default",
            "--definition",
            f"@{f}",
            "--force",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "(force)" in result.output
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    defn_mock = admin_bp.get_version.return_value.get_definition.return_value
    assert defn_mock.definition == payload
    defn_mock.save.assert_called_once_with(danger_zone_accepted=True)


def test_set_version_definition_without_force_rejects_dangerzone(
    patch_client, tmp_path
):
    f = tmp_path / "bv.json"
    f.write_text('{"id": {"blueprintId": "bp.custom.my_bp", "versionId": "bv.v1"}}')
    # Simulate backend dangerZone rejection
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    defn_mock = admin_bp.get_version.return_value.get_definition.return_value
    defn_mock.save.side_effect = Exception(
        "Blueprint version has existing artifacts and dangerZoneAccepted is false"
    )
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-version-definition",
            "bp.custom.my_bp",
            "bv.v1",
            "--definition",
            f"@{f}",
        ],
    )
    assert result.exit_code != 0
    assert "Save blocked" in result.output
    assert "--force" in result.output
    assert "create a new version" in result.output


def test_set_version_definition_rejects_non_object(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-version-definition",
            "bp.custom.my_bp",
            "bv.v1",
            "--definition",
            '["not", "an", "object"]',
        ],
    )
    assert result.exit_code != 0
    assert "JSON object" in result.output


# ---------------------------------------------------------------------------
# Structural lint: _lint_version_definition + set-version-definition warnings
# ---------------------------------------------------------------------------


def _clean_version_payload() -> dict:
    """A minimally well-formed blueprint version definition (no warnings)."""
    return {
        "fieldDefinitions": {
            "title": {"fieldType": "TEXT", "label": "Title"},
        },
        "workflowDefinition": {
            "stepDefinitions": [{"id": "draft", "name": "Draft"}],
            "initialStepId": "draft",
        },
        "logicalHookList": [],
        "actions": {},
        "uiDefinition": {
            "views": {
                "main": {
                    "label": "Overview",
                    "viewComponent": {
                        "type": "container",
                        "layout": {
                            "type": "sequential",
                            "viewComponents": [
                                {"type": "text-field", "fieldId": "title"},
                            ],
                        },
                    },
                }
            },
            "uiStepDefinitions": {"draft": {"viewId": "main"}},
            "artifactPageViewId": "main",
        },
    }


def test_lint_version_definition_clean_payload():
    from dku_cli.commands.govern_blueprint import _lint_version_definition

    assert _lint_version_definition(_clean_version_payload()) == []


def test_describe_version_builds_field_rows_with_metadata():
    from dku_cli.commands.govern_blueprint import _build_field_rows

    payload = _clean_version_payload()
    payload["fieldDefinitions"]["priority"] = {
        "fieldType": "CATEGORY",
        "label": "Priority",
        "sourceType": "USER",
        "listConfig": {},
        "isMandatory": True,
        "categories": ["Low", "High"],
    }

    rows = _build_field_rows(payload)
    row = next(r for r in rows if r["id"] == "priority")

    assert row["type"] == "CATEGORY"
    assert row["source"] == "USER"
    assert row["list"] == "*"
    assert row["required"] == "*"
    assert row["categories"] == "Low,High"


def test_describe_version_builds_view_rows_with_usage_and_component_counts():
    from dku_cli.commands.govern_blueprint import _build_view_rows

    payload = _clean_version_payload()
    payload["uiDefinition"]["uiStepDefinitions"]["review"] = {"viewId": "main"}
    payload["uiDefinition"]["views"]["secondary"] = {
        "label": "Secondary",
        "viewComponent": {"type": "text-field", "fieldId": "title"},
    }

    rows = _build_view_rows(payload)
    main = next(r for r in rows if r["id"] == "main")
    secondary = next(r for r in rows if r["id"] == "secondary")

    assert main["components"] == "1"
    assert main["is_artifact_page"] == "*"
    assert main["used_by_steps"] == "draft,review"
    assert secondary["components"] == "1"
    assert secondary["used_by_steps"] == "—"


def test_describe_version_builds_signoff_rows_and_warnings():
    from dku_cli.commands.govern_blueprint import (
        _build_signoff_rows,
        _describe_version_warnings,
    )

    signoff_rows = _build_signoff_rows(
        [
            MagicMock_wrapper(
                {
                    "id": {"stepId": "ghost"},
                    "title": "Review gate",
                    "mandatory": True,
                    "feedbackUsersGroups": ["govern-reviewers"],
                    "approvers": [
                        {"usersContainer": {"type": "GROUP"}},
                        {"usersContainer": {"type": "USER"}},
                    ],
                }
            )
        ]
    )

    assert signoff_rows == [
        {
            "step": "ghost",
            "title": "Review gate",
            "mandatory": "*",
            "approvers": "2",
            "approver_types": "GROUP,USER",
            "feedback_groups": "1",
        }
    ]
    warnings = _describe_version_warnings(
        _clean_version_payload(), {"draft"}, signoff_rows
    )
    assert any("Signoff configured on step 'ghost'" in w for w in warnings)


def test_describe_version_resolves_status_from_version_trace():
    from dku_cli.commands.govern_blueprint import _resolve_version_status

    bp = MagicMock()
    bp.list_versions.return_value = [
        MagicMock_wrapper(
            {
                "blueprintVersion": {
                    "id": {"blueprintId": "bp.x", "versionId": "bv.v1"}
                },
                "blueprintVersionTrace": {"status": "ACTIVE"},
            }
        )
    ]

    assert _resolve_version_status(bp, "bv.v1") == "ACTIVE"
    assert _resolve_version_status(bp, "bv.missing") == "?"


def test_lint_version_definition_flags_empty_views():
    from dku_cli.commands.govern_blueprint import _lint_version_definition

    payload = _clean_version_payload()
    payload["uiDefinition"]["views"] = {}
    payload["uiDefinition"]["artifactPageViewId"] = ""
    payload["uiDefinition"]["uiStepDefinitions"] = {"draft": {"viewId": ""}}

    warnings = _lint_version_definition(payload)
    joined = " | ".join(warnings)
    assert "views is empty" in joined
    assert "artifactPageViewId is empty" in joined
    # With views empty, the step-viewId check doesn't fire (there's nothing to
    # reference) — only the top-level empty-views + empty-page-id warnings.


def test_lint_version_definition_flags_dangling_artifact_page_view_id():
    from dku_cli.commands.govern_blueprint import _lint_version_definition

    payload = _clean_version_payload()
    payload["uiDefinition"]["artifactPageViewId"] = "ghost"

    warnings = _lint_version_definition(payload)
    assert any("ghost" in w and "does not match" in w for w in warnings)


def test_lint_version_definition_flags_empty_step_view_id():
    from dku_cli.commands.govern_blueprint import _lint_version_definition

    payload = _clean_version_payload()
    payload["uiDefinition"]["uiStepDefinitions"]["draft"] = {"viewId": ""}

    warnings = _lint_version_definition(payload)
    assert any("Step 'draft'" in w and "has no viewId" in w for w in warnings)


def test_lint_version_definition_flags_dangling_step_view_id():
    from dku_cli.commands.govern_blueprint import _lint_version_definition

    payload = _clean_version_payload()
    payload["uiDefinition"]["uiStepDefinitions"]["draft"] = {"viewId": "ghost"}

    warnings = _lint_version_definition(payload)
    assert any(
        "Step 'draft'" in w and "ghost" in w and "does not match" in w for w in warnings
    )


def test_lint_version_definition_flags_unreferenced_field():
    from dku_cli.commands.govern_blueprint import _lint_version_definition

    payload = _clean_version_payload()
    payload["fieldDefinitions"]["orphan"] = {
        "fieldType": "TEXT",
        "label": "Orphan",
    }

    warnings = _lint_version_definition(payload)
    assert any("Field 'orphan'" in w and "not referenced" in w for w in warnings)
    # 'title' is still referenced and should not be flagged
    assert not any("Field 'title'" in w for w in warnings)


def test_lint_version_definition_handles_non_dict_input():
    from dku_cli.commands.govern_blueprint import _lint_version_definition

    assert _lint_version_definition([]) == []  # type: ignore[arg-type]
    assert _lint_version_definition("nope") == []  # type: ignore[arg-type]


def test_set_version_definition_warns_on_empty_views(patch_client, tmp_path):
    """set-version-definition must surface structural warnings on push."""
    payload = _clean_version_payload()
    payload["uiDefinition"]["views"] = {}
    payload["uiDefinition"]["artifactPageViewId"] = ""
    payload["uiDefinition"]["uiStepDefinitions"] = {"draft": {"viewId": ""}}

    f = tmp_path / "bv.json"
    f.write_text(json.dumps(payload))
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-version-definition",
            "bp.custom.my_bp",
            "bv.v1",
            "--definition",
            f"@{f}",
        ],
    )
    assert result.exit_code == 0, result.output
    # Save still succeeds
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    defn_mock = designer.get_blueprint.return_value.get_version.return_value.get_definition.return_value
    defn_mock.save.assert_called_once_with(danger_zone_accepted=False)
    # But stderr carries the structural warnings (CliRunner mixes stderr into output)
    assert "structural issue" in result.output
    assert "views is empty" in result.output
    assert "artifactPageViewId is empty" in result.output
    assert "describe-version" in result.output


def test_set_version_definition_no_warning_on_clean_push(patch_client, tmp_path):
    """A well-formed payload produces no structural-warning banner."""
    payload = _clean_version_payload()
    f = tmp_path / "bv.json"
    f.write_text(json.dumps(payload))
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-version-definition",
            "bp.custom.my_bp",
            "bv.v1",
            "--definition",
            f"@{f}",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Saved definition" in result.output
    assert "structural issue" not in result.output
    assert "views is empty" not in result.output


def test_delete_version_requires_confirm(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "delete-version",
            "bp.custom.my_bp",
            "bv.v1",
        ],
    )
    combined = result.output + (result.stderr or "")
    assert result.exit_code == 77
    assert "blocked" in combined.lower()


def test_delete_version_with_confirm(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "delete-version",
            "bp.custom.my_bp",
            "bv.v1",
            "--confirm",
        ],
    )
    assert result.exit_code == 0, result.output
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    admin_bp.get_version.return_value.delete.assert_called_once()


def test_version_status_json(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "version-status",
            "bp.system.govern_project",
            "bv.system.default",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "ACTIVE"


def test_set_version_status_active(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-version-status",
            "bp.custom.my_bp",
            "bv.v1",
            "ACTIVE",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "ACTIVE" in result.output
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    trace_mock = admin_bp.get_version.return_value.get_trace.return_value
    trace_mock.set_status.assert_called_once_with("ACTIVE")


def test_set_version_status_rejects_unknown(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-version-status",
            "bp.custom.my_bp",
            "bv.v1",
            "PUBLISHED",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_set_version_status_case_insensitive(patch_client):
    """case_sensitive=False: a lowercase status is accepted and normalized to the
    canonical uppercase value passed to the Govern trace."""
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-version-status",
            "bp.custom.my_bp",
            "bv.v1",
            "draft",
        ],
    )
    assert result.exit_code == 0, result.output
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    trace_mock = admin_bp.get_version.return_value.get_trace.return_value
    trace_mock.set_status.assert_called_once_with("DRAFT")


# ---------------------------------------------------------------------------
# Signoff configuration designer
# ---------------------------------------------------------------------------


def test_list_signoff_configs(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "list-signoff-configs",
            "bp.system.govern_project",
            "bv.system.default",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "review" in result.output
    assert "Review gate" in result.output


def test_list_signoff_configs_json(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "list-signoff-configs",
            "bp.system.govern_project",
            "bv.system.default",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["step"] == "review"
    assert data[0]["mandatory"] == "*"
    assert data[0]["feedback_groups"] == "1"


def test_get_signoff_config(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "get-signoff-config",
            "bp.system.govern_project",
            "bv.system.default",
            "review",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["title"] == "Review gate"
    assert data["id"]["stepId"] == "review"


def test_create_signoff_config_strips_id(patch_client):
    body = {
        "id": {"should": "be stripped"},
        "title": "New signoff",
        "mandatory": True,
        "feedbackUsersGroups": [],
        "approvers": [],
    }
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "create-signoff-config",
            "bp.custom.my_bp",
            "bv.v1",
            "review",
            "--definition",
            json.dumps(body),
        ],
    )
    assert result.exit_code == 0, result.output
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    version = admin_bp.get_version.return_value
    version.create_signoff_configuration.assert_called_once()
    call_args = version.create_signoff_configuration.call_args
    assert call_args[0][0] == "review"
    assert "id" not in call_args[0][1]
    assert call_args[0][1]["title"] == "New signoff"


def test_set_signoff_config(patch_client, tmp_path):
    body = {
        "title": "Updated",
        "mandatory": False,
        "feedbackUsersGroups": [],
        "approvers": [],
    }
    f = tmp_path / "so.json"
    f.write_text(json.dumps(body))
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-signoff-config",
            "bp.custom.my_bp",
            "bv.v1",
            "review",
            "--definition",
            f"@{f}",
        ],
    )
    assert result.exit_code == 0, result.output
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    version = admin_bp.get_version.return_value
    signoff = version.get_signoff_configuration.return_value
    defn = signoff.get_definition.return_value
    assert defn.definition == body
    defn.save.assert_called_once()


def test_delete_signoff_config_requires_confirm(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "delete-signoff-config",
            "bp.custom.my_bp",
            "bv.v1",
            "review",
        ],
    )
    combined = result.output + (result.stderr or "")
    assert result.exit_code == 77
    assert "blocked" in combined.lower()


def test_delete_signoff_config_with_confirm(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "delete-signoff-config",
            "bp.custom.my_bp",
            "bv.v1",
            "review",
            "--confirm",
        ],
    )
    assert result.exit_code == 0, result.output
    designer = (
        patch_client.get_govern_client.return_value.get_blueprint_designer.return_value
    )
    admin_bp = designer.get_blueprint.return_value
    version = admin_bp.get_version.return_value
    version.get_signoff_configuration.return_value.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Import / Export version
# ---------------------------------------------------------------------------


def test_export_version_wraps_definition_trace_and_signoffs(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "export-version",
            "bp.system.govern_project",
            "bv.system.default",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    envelope = json.loads(result.output)
    assert "blueprintVersion" in envelope
    assert envelope["blueprintVersion"]["name"] == "Default"
    # Origin version ID is pulled from the trace — None in the default fixture
    assert "originVersionId" in envelope
    # Signoffs list is populated from list_signoff_configurations()
    assert isinstance(envelope["signoffsConfigurations"], list)
    assert len(envelope["signoffsConfigurations"]) == 1
    assert envelope["signoffsConfigurations"][0]["title"] == "Review gate"


def test_export_version_strips_non_role_users_by_default(patch_client):
    """Non-role reviewers are dropped on import — export filters them too by default."""
    gov = patch_client.get_govern_client.return_value
    designer = gov.get_blueprint_designer.return_value
    admin_bp = designer.get_blueprint.return_value
    version = admin_bp.get_version.return_value
    # Inject a signoff config with a mix of user/group/role reviewers
    mixed_item = MagicMock_wrapper(
        {
            "id": {
                "blueprintVersionId": {
                    "blueprintId": "bp.x",
                    "versionId": "bv.v1",
                },
                "stepId": "review",
            },
            "title": "Mixed",
            "feedbackUsersGroups": [
                {
                    "id": "g1",
                    "title": "Group 1",
                    "users": [
                        {"usersContainer": {"type": "user", "login": "alice"}},
                        {"usersContainer": {"type": "role", "roleId": "ro.reviewer"}},
                    ],
                }
            ],
            "approvers": [
                {"usersContainer": {"type": "group", "groupName": "approvers"}},
                {"usersContainer": {"type": "role", "roleId": "ro.final"}},
            ],
        }
    )
    version.list_signoff_configurations.return_value = [mixed_item]

    result = runner.invoke(
        app,
        ["govern", "blueprint", "export-version", "bp.x", "bv.v1", "-o", "json"],
    )
    assert result.exit_code == 0, result.output
    envelope = json.loads(result.output)
    s = envelope["signoffsConfigurations"][0]
    # Only role users survive the default filter
    assert len(s["feedbackUsersGroups"][0]["users"]) == 1
    assert s["feedbackUsersGroups"][0]["users"][0]["usersContainer"]["type"] == "role"
    assert len(s["approvers"]) == 1
    assert s["approvers"][0]["usersContainer"]["type"] == "role"


def test_export_version_keep_non_role_users_flag(patch_client):
    """--keep-non-role-users preserves all reviewer types verbatim."""
    gov = patch_client.get_govern_client.return_value
    designer = gov.get_blueprint_designer.return_value
    admin_bp = designer.get_blueprint.return_value
    version = admin_bp.get_version.return_value
    mixed_item = MagicMock_wrapper(
        {
            "id": {
                "blueprintVersionId": {
                    "blueprintId": "bp.x",
                    "versionId": "bv.v1",
                },
                "stepId": "review",
            },
            "title": "Mixed",
            "feedbackUsersGroups": [
                {
                    "id": "g1",
                    "title": "Group 1",
                    "users": [
                        {"usersContainer": {"type": "user", "login": "alice"}},
                    ],
                }
            ],
            "approvers": [],
        }
    )
    version.list_signoff_configurations.return_value = [mixed_item]

    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "export-version",
            "bp.x",
            "bv.v1",
            "--keep-non-role-users",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    envelope = json.loads(result.output)
    s = envelope["signoffsConfigurations"][0]
    assert len(s["feedbackUsersGroups"][0]["users"]) == 1
    assert s["feedbackUsersGroups"][0]["users"][0]["usersContainer"]["type"] == "user"


def test_import_version_happy_path(patch_client):
    envelope = {
        "blueprintVersion": {
            "id": {"blueprintId": "bp.custom.my_bp", "versionId": "bv.v2"},
            "name": "Version 2",
            "fieldDefinitions": {},
            "workflowDefinition": {"stepDefinitions": []},
        },
        "originVersionId": "bv.v1",
        "signoffsConfigurations": [],
    }
    # Stub the private _perform_json on the govern client
    gov = patch_client.get_govern_client.return_value
    gov._perform_json.return_value = {
        "blueprintVersion": {
            "id": {"blueprintId": "bp.custom.my_bp", "versionId": "bv.v2"}
        }
    }
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "import-version",
            "bp.custom.my_bp",
            "--definition",
            json.dumps(envelope),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Imported version 'bv.v2'" in result.output
    call = gov._perform_json.call_args
    assert call[0][0] == "POST"
    assert call[0][1] == "/admin/blueprint/bp.custom.my_bp/versions/import"
    assert call.kwargs["params"].get("signoffImportRoles") == "ALL"
    assert (
        call.kwargs["body"]["blueprintVersion"]["id"]["blueprintId"]
        == "bp.custom.my_bp"
    )


def test_import_version_rewrites_blueprint_id_in_body(patch_client):
    """Cross-blueprint import: body's id.blueprintId is rewritten to match URL."""
    envelope = {
        "blueprintVersion": {
            "id": {"blueprintId": "bp.SOURCE", "versionId": "bv.v1"},
            "name": "x",
        }
    }
    gov = patch_client.get_govern_client.return_value
    gov._perform_json.return_value = {
        "blueprintVersion": {"id": {"blueprintId": "bp.TARGET", "versionId": "bv.v1"}}
    }
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "import-version",
            "bp.TARGET",
            "--definition",
            json.dumps(envelope),
        ],
    )
    assert result.exit_code == 0, result.output
    call = gov._perform_json.call_args
    assert call.kwargs["body"]["blueprintVersion"]["id"]["blueprintId"] == "bp.TARGET"


def test_import_version_rewrites_signoff_config_ids(patch_client):
    """Signoff config IDs must be rewritten to match the target blueprint,
    otherwise the server's performSignoffsConfigurationsImport validation fails
    (`the blueprint version id specified in the sign-off configuration must
    match the outer blueprint version id`)."""
    envelope = {
        "blueprintVersion": {
            "id": {"blueprintId": "bp.SOURCE", "versionId": "bv.v1"},
            "name": "x",
        },
        "signoffsConfigurations": [
            {
                "id": {
                    "blueprintVersionId": {
                        "blueprintId": "bp.SOURCE",
                        "versionId": "bv.v1",
                    },
                    "stepId": "review",
                },
                "title": "Review",
            }
        ],
    }
    gov = patch_client.get_govern_client.return_value
    gov._perform_json.return_value = {
        "blueprintVersion": {"id": {"blueprintId": "bp.TARGET", "versionId": "bv.v1"}}
    }
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "import-version",
            "bp.TARGET",
            "--definition",
            json.dumps(envelope),
        ],
    )
    assert result.exit_code == 0, result.output
    body = gov._perform_json.call_args.kwargs["body"]
    signoff = body["signoffsConfigurations"][0]
    assert signoff["id"]["blueprintVersionId"]["blueprintId"] == "bp.TARGET"
    assert signoff["id"]["blueprintVersionId"]["versionId"] == "bv.v1"
    assert signoff["id"]["stepId"] == "review"


def test_import_version_forwards_flags(patch_client):
    envelope = {
        "blueprintVersion": {"id": {"blueprintId": "bp.x", "versionId": "bv.v1"}}
    }
    gov = patch_client.get_govern_client.return_value
    gov._perform_json.return_value = {
        "blueprintVersion": {"id": {"blueprintId": "bp.x", "versionId": "bv.v1"}}
    }
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "import-version",
            "bp.x",
            "--definition",
            json.dumps(envelope),
            "--ignore-origin-errors",
            "--signoff-roles",
            "EXISTING",
            "--migration-behavior",
            "IMPORT_WITHOUT_MIGRATIONS",
        ],
    )
    assert result.exit_code == 0, result.output
    params = gov._perform_json.call_args.kwargs["params"]
    assert params["ignoreOriginVersionErrors"] == "true"
    assert params["signoffImportRoles"] == "EXISTING"
    assert params["migrationPathImportBehavior"] == "IMPORT_WITHOUT_MIGRATIONS"


def test_import_version_rejects_missing_blueprintVersion(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "import-version",
            "bp.x",
            "--definition",
            json.dumps({"originVersionId": "bv.v1"}),
        ],
    )
    assert result.exit_code != 0
    out = result.output + (result.stderr or "")
    assert "blueprintVersion" in out


def test_import_version_rejects_invalid_signoff_roles(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "import-version",
            "bp.x",
            "--definition",
            '{"blueprintVersion": {"id": {"blueprintId": "bp.x", "versionId": "bv.v1"}}}',
            "--signoff-roles",
            "WHATEVER",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_import_version_rejects_invalid_migration_behavior(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "import-version",
            "bp.x",
            "--definition",
            '{"blueprintVersion": {"id": {"blueprintId": "bp.x", "versionId": "bv.v1"}}}',
            "--migration-behavior",
            "BOGUS",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in result.output


# ---------------------------------------------------------------------------
# Hooks surfacing: describe-version Hooks section + list-hooks verb.
#
# Backstory: agents that sweep blueprints looking for `hooks` always returned
# zero because hooks live on the VERSION under `logicalHookList`. Even after
# drilling to describe-version, hooks weren't rendered. Both behaviours are
# now under test to prevent regression.
# ---------------------------------------------------------------------------


def _inject_version_def(patch_client, payload: dict) -> None:
    """Override the wired bp_ver definition with a custom payload.

    Mutates both the designer path (used by describe-version) and the direct
    path (used by list-hooks). They share the same bp_ver mock so a single
    assignment covers both.
    """
    govern = patch_client.get_govern_client.return_value
    bp_obj = govern.get_blueprint.return_value
    bp_ver = bp_obj.get_version.return_value
    bp_ver.get_definition.return_value.get_raw.return_value = payload


_HOOK_VER_PAYLOAD = {
    "id": {"blueprintId": "bp.hook_test", "versionId": "bv.default"},
    "name": "Default",
    "fieldDefinitions": {},
    "workflowDefinition": {"stepDefinitions": [{"id": "draft", "name": "Draft"}]},
    "logicalHookList": [
        {
            "name": "compute_score",
            "description": "Derive derived_score from risk_level.",
            "phases": ["CREATE", "UPDATE"],
            "script": "x = 1\ny = 2\nz = 3\n",
        },
        {
            "name": "validate_owner",
            "description": "Block save when high-risk artifact has no owner.",
            "phases": ["UPDATE"],
            "script": "raise ValueError('nope')\n",
        },
    ],
    "uiDefinition": {
        "views": {"main": {"label": "Overview", "viewComponent": {}}},
        "uiStepDefinitions": {"draft": {"viewId": "main"}},
        "artifactPageViewId": "main",
    },
}


def test_describe_version_renders_hooks_section(patch_client):
    _inject_version_def(patch_client, _HOOK_VER_PAYLOAD)
    result = runner.invoke(
        app,
        ["govern", "blueprint", "describe-version", "bp.hook_test", "bv.default"],
    )
    assert result.exit_code == 0, result.output
    # Section header counts the hooks
    assert "Hooks (2)" in result.output
    # Both hook names render
    assert "compute_score" in result.output
    assert "validate_owner" in result.output
    # Phases column renders as comma-joined string
    assert "CREATE,UPDATE" in result.output


def test_describe_version_hooks_section_zero_when_absent(patch_client):
    payload = dict(_HOOK_VER_PAYLOAD)
    payload["logicalHookList"] = []
    _inject_version_def(patch_client, payload)
    result = runner.invoke(
        app,
        ["govern", "blueprint", "describe-version", "bp.hook_test", "bv.default"],
    )
    assert result.exit_code == 0, result.output
    assert "Hooks (0)" in result.output


def test_list_hooks_table(patch_client):
    _inject_version_def(patch_client, _HOOK_VER_PAYLOAD)
    result = runner.invoke(
        app,
        ["govern", "blueprint", "list-hooks", "bp.hook_test", "bv.default"],
    )
    assert result.exit_code == 0, result.output
    assert "compute_score" in result.output
    assert "validate_owner" in result.output
    assert "CREATE,UPDATE" in result.output
    # Lines column reflects script length (3 lines for compute_score)
    assert "3" in result.output


def test_list_hooks_json(patch_client):
    _inject_version_def(patch_client, _HOOK_VER_PAYLOAD)
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "list-hooks",
            "bp.hook_test",
            "bv.default",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 2
    # JSON output preserves the FULL hook including the script source — that's
    # the agent's path when it needs to inspect what a hook actually does.
    assert data[0]["name"] == "compute_score"
    assert "script" in data[0]
    assert "x = 1" in data[0]["script"]


def test_list_hooks_empty_emits_helpful_message(patch_client):
    payload = dict(_HOOK_VER_PAYLOAD)
    payload["logicalHookList"] = []
    _inject_version_def(patch_client, payload)
    result = runner.invoke(
        app,
        ["govern", "blueprint", "list-hooks", "bp.hook_test", "bv.default"],
    )
    assert result.exit_code == 0, result.output
    assert "No hooks configured" in result.output
    assert "bp.hook_test" in result.output


def test_list_hooks_empty_json_returns_empty_array(patch_client):
    payload = dict(_HOOK_VER_PAYLOAD)
    payload["logicalHookList"] = []
    _inject_version_def(patch_client, payload)
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "list-hooks",
            "bp.hook_test",
            "bv.default",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == []


def test_list_hooks_drops_non_dict_entries(patch_client):
    """Defensive: malformed payloads (non-dict items) must not crash the table."""
    payload = dict(_HOOK_VER_PAYLOAD)
    payload["logicalHookList"] = [
        {"name": "good", "phases": ["CREATE"], "script": "pass\n"},
        "this is not a dict",
        None,
        42,
    ]
    _inject_version_def(patch_client, payload)
    result = runner.invoke(
        app,
        ["govern", "blueprint", "list-hooks", "bp.hook_test", "bv.default"],
    )
    assert result.exit_code == 0, result.output
    assert "good" in result.output
    # The non-dict entries are silently dropped — header reports a count of 1.
    assert "Hooks on bp.hook_test (bv.default) — 1" in result.output


def test_summarize_hook_truncates_long_descriptions():
    from dku_cli.commands.govern_blueprint import _summarize_hook

    long = "x" * 200
    row = _summarize_hook(
        {"name": "h", "description": long, "phases": [], "script": ""}
    )
    # Truncated to 61 chars + ellipsis = 62 displayed
    assert row["description"].endswith("…")
    assert len(row["description"]) <= 62
