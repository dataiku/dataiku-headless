"""Tests for the complete Project Standards command surface."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()

CHECK_ID = "Projectmusthaveadescription"
ELEMENT_TYPE = "project_standards_check_spec_project-standards_project-description"
SCOPE_NAME = "Governed"


def _admin_flags(target: str) -> list[str]:
    return ["--yes", "--confirm-name", target, "--i-know-what-im-doing"]


@pytest.fixture
def ps(patch_client):
    standards = patch_client.get_project_standards.return_value
    spec_raw = {
        "elementType": ELEMENT_TYPE,
        "label": "Project must have a description",
        "description": "Check the project description",
        "ownerPluginId": "project-standards",
        "parameters": [{"name": "minimumLength", "type": "INT"}],
    }
    check_raw = {
        "id": CHECK_ID,
        "name": "Project must have a description",
        "description": "Check the project description",
        "checkElementType": ELEMENT_TYPE,
        "checkParams": {},
        "tags": ["governance"],
    }
    scope_raw = {
        "name": SCOPE_NAME,
        "description": "Production projects",
        "checks": [CHECK_ID],
        "selectionMethod": "BY_PROJECT",
        "selectedProjects": ["PROJ1"],
        "selectedFolders": [],
        "selectedTags": [],
    }
    default_raw = {
        "name": "Default",
        "description": "Fallback",
        "checks": [CHECK_ID],
        "selectionMethod": "ALL",
        "selectedProjects": [],
        "selectedFolders": [],
        "selectedTags": [],
    }

    check = MagicMock()
    check.id = CHECK_ID
    check.name = check_raw["name"]
    check.description = check_raw["description"]
    check.check_params = check_raw["checkParams"]
    check.tags = check_raw["tags"]
    check.get_raw.return_value = check_raw

    scope = MagicMock()
    scope.name = SCOPE_NAME
    scope.description = scope_raw["description"]
    scope.selection_method = scope_raw["selectionMethod"]
    scope.selected_projects = list(scope_raw["selectedProjects"])
    scope.selected_folders = []
    scope.selected_tags = []
    scope.checks = list(scope_raw["checks"])
    scope.is_default = False
    scope.get_raw.return_value = scope_raw

    default_scope = MagicMock()
    default_scope.name = "Default"
    default_scope.is_default = True
    default_scope.selection_method = "ALL"
    default_scope.checks = list(default_raw["checks"])
    default_scope.get_raw.return_value = default_raw

    state = {
        "check_deleted": False,
        "scope_deleted": False,
        "scope_order": [scope_raw, default_raw],
    }

    def list_checks(as_type="listitems"):
        if state["check_deleted"]:
            return []
        return [check] if as_type == "objects" else [SimpleNamespace(id=CHECK_ID)]

    def list_scopes(as_type="listitems"):
        del as_type
        return [default_raw] if state["scope_deleted"] else list(state["scope_order"])

    check.delete.side_effect = lambda: state.update(check_deleted=True)
    scope.delete.side_effect = lambda: state.update(scope_deleted=True)
    scope.save.side_effect = lambda: scope_raw.update(
        description=scope.description,
        checks=list(scope.checks),
        selectionMethod=scope.selection_method,
        selectedProjects=list(scope.selected_projects),
        selectedFolders=list(scope.selected_folders),
        selectedTags=list(scope.selected_tags),
    )
    default_scope.save.side_effect = lambda: default_raw.update(
        checks=list(default_scope.checks)
    )
    standards.list_check_specs.return_value = [spec_raw]
    standards.list_checks.side_effect = list_checks
    standards.get_check.return_value = check
    standards.create_checks.return_value = [check]
    standards.list_scopes.side_effect = list_scopes
    standards.get_scope.side_effect = lambda name: (
        default_scope if name == "Default" else scope
    )
    standards.get_default_scope.return_value = default_scope
    standards.create_scope.return_value = scope

    project = patch_client.get_project.return_value
    project.get_project_standards_scope.return_value = SCOPE_NAME
    return SimpleNamespace(
        standards=standards,
        check=check,
        scope=scope,
        default_scope=default_scope,
        state=state,
        project=project,
    )


def _report(*, severity: int = 0, status: str = "RUN_SUCCESS"):
    message = "Project is compliant" if severity == 0 else "Description missing"
    report = MagicMock()
    report.data = {
        "projectKey": "PROJ1",
        "scope": SCOPE_NAME,
        "bundleChecksRunInfo": {
            CHECK_ID: {
                "check": {"id": CHECK_ID, "name": "Project must have a description"},
                "result": {
                    "status": status,
                    "severity": severity,
                    "message": message,
                },
                "durationMs": 12,
            }
        },
    }
    return report


def test_help_lists_complete_flat_surface_and_enums():
    group = runner.invoke(app, ["project-standards", "--help"])
    assert group.exit_code == 0
    commands = json.loads(group.stdout)["commands"]
    assert {
        "create-checks",
        "update-check",
        "delete-check",
        "create-scope",
        "update-scope",
        "reorder-scope",
        "delete-scope",
        "project-scope",
        "run",
        "last-report",
    } <= set(commands)

    create = runner.invoke(app, ["project-standards", "create-scope", "--help"])
    options = {item["name"]: item for item in json.loads(create.stdout)["options"]}
    assert options["selection_method"]["choices"] == [
        "BY_PROJECT",
        "BY_FOLDER",
        "BY_TAG",
    ]

    run = runner.invoke(app, ["project-standards", "run", "--help"])
    options = {item["name"]: item for item in json.loads(run.stdout)["options"]}
    assert options["fail_at"]["choices"] == [
        "LOWEST",
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ]


def test_list_specs_and_checks_include_configuration(ps):
    specs = runner.invoke(
        app, ["--format", "json", "project-standards", "list-check-specs"]
    )
    assert specs.exit_code == 0
    assert json.loads(specs.stdout)[0]["parameters"][0]["name"] == "minimumLength"

    checks = runner.invoke(
        app, ["--format", "json", "project-standards", "list-checks"]
    )
    assert checks.exit_code == 0
    parsed = json.loads(checks.stdout)[0]
    assert parsed["id"] == CHECK_ID
    assert parsed["tags"] == ["governance"]


def test_get_check_returns_full_definition(ps):
    result = runner.invoke(app, ["project-standards", "get-check", CHECK_ID])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["checkElementType"] == ELEMENT_TYPE


def test_create_checks_is_tier_four_guarded(ps):
    args = ["project-standards", "create-checks", "--spec", ELEMENT_TYPE]
    blocked = runner.invoke(app, args)
    assert blocked.exit_code == 77
    ps.standards.create_checks.assert_not_called()

    allowed = runner.invoke(app, [*args, *_admin_flags("checks-library")])
    assert allowed.exit_code == 0
    ps.standards.create_checks.assert_called_once_with(
        [ELEMENT_TYPE], as_type="objects"
    )
    assert CHECK_ID in allowed.stdout


def test_update_check_parses_params_and_serializes_writes(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "update-check",
            CHECK_ID,
            "--params",
            '{"minimumLength":10}',
            "--tags",
            "quality, prod",
            *_admin_flags(CHECK_ID),
        ],
    )
    assert result.exit_code == 0
    assert ps.check.check_params == {"minimumLength": 10}
    assert ps.check.tags == ["quality", "prod"]
    ps.check.save.assert_called_once()


def test_update_check_renders_persisted_server_state(ps):
    persisted = MagicMock()
    persisted.get_raw.return_value = {
        "id": CHECK_ID,
        "name": "Normalized by DSS",
        "checkParams": {"minimumLength": 10},
    }
    ps.standards.get_check.side_effect = [ps.check, ps.check, persisted]

    result = runner.invoke(
        app,
        [
            "project-standards",
            "update-check",
            CHECK_ID,
            "--name",
            "requested",
            *_admin_flags(CHECK_ID),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["name"] == "Normalized by DSS"


def test_update_check_rejects_non_object_params(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "update-check",
            CHECK_ID,
            "--params",
            "[]",
            *_admin_flags(CHECK_ID),
        ],
    )
    assert result.exit_code == 1
    assert "JSON object" in result.output
    ps.check.save.assert_not_called()


def test_delete_check_refuses_dangling_reference(ps):
    result = runner.invoke(
        app,
        ["project-standards", "delete-check", CHECK_ID, *_admin_flags(CHECK_ID)],
    )
    assert result.exit_code == 1
    assert SCOPE_NAME in result.output
    assert "dangling" in result.output
    ps.check.delete.assert_not_called()


def test_force_delete_removes_scope_reference_first(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "delete-check",
            CHECK_ID,
            "--force",
            *_admin_flags(CHECK_ID),
        ],
    )
    assert result.exit_code == 0
    assert ps.scope.checks == []
    ps.scope.save.assert_called_once()
    ps.check.delete.assert_called_once()


def test_force_delete_refuses_reference_added_before_final_scan(ps):
    calls = 0

    def list_scopes(as_type="listitems"):
        nonlocal calls
        del as_type
        calls += 1
        if calls == 3:
            return [
                {
                    "name": "RacingScope",
                    "checks": [CHECK_ID],
                    "selectionMethod": "BY_TAG",
                }
            ]
        return ps.state["scope_order"]

    ps.standards.list_scopes.side_effect = list_scopes
    result = runner.invoke(
        app,
        [
            "project-standards",
            "delete-check",
            CHECK_ID,
            "--force",
            *_admin_flags(CHECK_ID),
        ],
    )

    assert result.exit_code == 1
    assert "RacingScope" in result.output
    ps.check.delete.assert_not_called()


def test_scope_reads_return_targets_and_default(ps):
    listed = runner.invoke(
        app, ["--format", "json", "project-standards", "list-scopes"]
    )
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)[0]["items"] == ["PROJ1"]

    got = runner.invoke(app, ["project-standards", "get-scope", SCOPE_NAME])
    assert json.loads(got.stdout)["selectedProjects"] == ["PROJ1"]

    default = runner.invoke(app, ["project-standards", "get-default-scope"])
    assert json.loads(default.stdout)["selectionMethod"] == "ALL"


def test_create_scope_is_guarded_and_typed(ps):
    args = [
        "project-standards",
        "create-scope",
        "--name",
        "FolderScope",
        "--selection-method",
        "by_folder",
        "--item",
        "folder1",
        "--check",
        CHECK_ID,
    ]
    assert runner.invoke(app, args).exit_code == 77

    allowed = runner.invoke(app, [*args, *_admin_flags("FolderScope")])
    assert allowed.exit_code == 0
    ps.standards.create_scope.assert_called_once_with(
        "FolderScope",
        description="",
        checks=[CHECK_ID],
        selection_method="BY_FOLDER",
        items=["folder1"],
    )


def test_create_scope_if_not_exists_skips_admin_guard(ps):
    result = runner.invoke(
        app,
        ["project-standards", "create-scope", "--name", SCOPE_NAME, "--if-not-exists"],
    )
    assert result.exit_code == 0
    ps.standards.create_scope.assert_not_called()
    assert json.loads(result.stdout)["name"] == SCOPE_NAME


def test_update_scope_replaces_selector_atomically(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "update-scope",
            SCOPE_NAME,
            "--selection-method",
            "BY_TAG",
            "--item",
            "production",
            *_admin_flags(SCOPE_NAME),
        ],
    )
    assert result.exit_code == 0
    assert ps.scope.selection_method == "BY_TAG"
    assert ps.scope.selected_projects == []
    assert ps.scope.selected_tags == ["production"]
    ps.scope.save.assert_called_once()


def test_update_scope_renders_persisted_server_state(ps):
    persisted = MagicMock()
    persisted.get_raw.return_value = {
        "name": SCOPE_NAME,
        "description": "Normalized by DSS",
        "checks": [CHECK_ID],
        "selectionMethod": "BY_PROJECT",
        "selectedProjects": ["PROJ1"],
        "selectedFolders": [],
        "selectedTags": [],
    }
    ps.standards.get_scope.side_effect = [ps.scope, ps.scope, persisted]

    result = runner.invoke(
        app,
        [
            "project-standards",
            "update-scope",
            SCOPE_NAME,
            "--description",
            "requested",
            *_admin_flags(SCOPE_NAME),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["description"] == "Normalized by DSS"


def test_update_scope_requires_new_items_with_new_method(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "update-scope",
            SCOPE_NAME,
            "--selection-method",
            "BY_TAG",
            *_admin_flags(SCOPE_NAME),
        ],
    )
    assert result.exit_code == 1
    assert "requires --item or --clear-items" in result.output
    ps.scope.save.assert_not_called()


def test_default_scope_allows_only_check_updates(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "update-scope",
            "Default",
            "--description",
            "new",
            *_admin_flags("Default"),
        ],
    )
    assert result.exit_code == 1
    assert "immutable" in result.output
    ps.default_scope.save.assert_not_called()


def test_reorder_scope_verifies_actual_order(ps):
    def reorder(_index):
        ps.state["scope_order"] = [
            {"name": "Other", "selectionMethod": "BY_TAG", "checks": []},
            ps.state["scope_order"][0],
            ps.state["scope_order"][1],
        ]

    ps.scope.reorder.side_effect = reorder
    result = runner.invoke(
        app,
        [
            "project-standards",
            "reorder-scope",
            SCOPE_NAME,
            "1",
            *_admin_flags(SCOPE_NAME),
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["actual_index"] == 1
    assert parsed["order"][-1] == "Default"


def test_delete_scope_is_guarded_and_verified(ps):
    blocked = runner.invoke(app, ["project-standards", "delete-scope", SCOPE_NAME])
    assert blocked.exit_code == 77
    ps.scope.delete.assert_not_called()

    allowed = runner.invoke(
        app,
        ["project-standards", "delete-scope", SCOPE_NAME, *_admin_flags(SCOPE_NAME)],
    )
    assert allowed.exit_code == 0
    ps.scope.delete.assert_called_once()


def test_project_scope_uses_environment_resolution(ps, monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["project-standards", "project-scope"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"project": "PROJ1", "scope": SCOPE_NAME}


def test_run_waits_and_prints_compliance_report(ps):
    future = ps.project.start_run_project_standards_checks.return_value
    future.wait_for_result.return_value = _report()
    result = runner.invoke(app, ["project-standards", "run", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert CHECK_ID in result.stdout
    assert "RUN_SUCCESS" in result.stdout
    ps.project.start_run_project_standards_checks.assert_called_once_with(
        check_ids=None
    )


def test_explicit_run_accepts_legacy_and_short_check_flags(ps):
    future = ps.project.start_run_project_standards_checks.return_value
    future.wait_for_result.return_value = _report()
    result = runner.invoke(
        app,
        [
            "project-standards",
            "run",
            "--check-id",
            CHECK_ID,
            "--check",
            CHECK_ID,
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    ps.project.start_run_project_standards_checks.assert_called_once_with(
        check_ids=[CHECK_ID, CHECK_ID]
    )
    assert "do not update last-report" in result.stderr


def test_no_wait_preserves_existing_async_behavior(ps):
    future = ps.project.start_run_project_standards_checks.return_value
    future.job_id = "future-42"
    result = runner.invoke(
        app, ["project-standards", "run", "--no-wait", "-P", "PROJ1"]
    )
    assert result.exit_code == 0
    future.wait_for_result.assert_not_called()
    assert "future-42" in result.stderr


@pytest.mark.parametrize(
    ("severity", "threshold", "expected_exit"),
    [(3, "HIGH", 0), (4, "HIGH", 1), (5, "MEDIUM", 1)],
)
def test_run_optional_ci_threshold(ps, severity, threshold, expected_exit):
    future = ps.project.start_run_project_standards_checks.return_value
    future.wait_for_result.return_value = _report(severity=severity)
    result = runner.invoke(
        app,
        ["project-standards", "run", "--fail-at", threshold, "-P", "PROJ1"],
    )
    assert result.exit_code == expected_exit
    assert CHECK_ID in result.stdout


def test_fail_at_requires_wait(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "run",
            "--fail-at",
            "HIGH",
            "--no-wait",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 1
    assert "requires --wait" in result.stderr
    ps.project.start_run_project_standards_checks.assert_not_called()


def test_run_fails_when_check_execution_errors(ps):
    future = ps.project.start_run_project_standards_checks.return_value
    future.wait_for_result.return_value = _report(status="RUN_ERROR")
    result = runner.invoke(app, ["project-standards", "run", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "failed to execute" in result.stderr


def test_last_report_and_missing_report_hint(ps):
    ps.project.get_project_standards_last_report.return_value = _report()
    result = runner.invoke(app, ["project-standards", "last-report", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert CHECK_ID in result.stdout

    ps.project.get_project_standards_last_report.return_value = None
    missing = runner.invoke(app, ["project-standards", "last-report", "-P", "PROJ1"])
    assert missing.exit_code == 1
    assert "project-standards run -P PROJ1" in missing.output
