"""Tests for project-standards commands (DSS 14.1+ Project Standards)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from dataikuapi.dss.project_standards import (
    DSSProjectStandardsCheckListItem,
    DSSProjectStandardsRunReport,
    DSSProjectStandardsScope,
)
from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


@pytest.fixture
def ps(patch_client):
    """Wire a project-standards handle mock onto the shared mock client."""
    handle = MagicMock()
    patch_client.get_project_standards.return_value = handle

    handle.list_check_specs.return_value = [
        {
            "elementType": "project_standards_check_spec_project-standards_datasets",
            "label": "Datasets are documented",
            "description": "Every dataset has a description",
            "ownerPluginId": "project-standards",
        }
    ]
    handle.list_checks.return_value = [
        DSSProjectStandardsCheckListItem(
            patch_client,
            {
                "id": "check1",
                "name": "Datasets are documented",
                "description": "",
                "checkElementType": (
                    "project_standards_check_spec_project-standards_datasets"
                ),
            },
        )
    ]
    handle.create_checks.return_value = handle.list_checks.return_value
    handle.list_scopes.return_value = [
        {
            "name": "Default",
            "description": "",
            "checks": ["check1"],
            "selectionMethod": "ALL",
        }
    ]
    handle.create_scope.return_value = DSSProjectStandardsScope(
        patch_client, {"name": "myscope", "selectionMethod": "BY_PROJECT"}
    )
    return handle


_RAW_REPORT = {
    "projectKey": "PROJ1",
    "bundleChecksRunInfo": {
        "check1": {
            "check": {"id": "check1", "name": "Datasets are documented"},
            "result": {
                "status": "RUN_SUCCESS",
                "severity": 3,
                "message": "2 datasets have no description",
            },
        },
        "check2": {
            "check": {"id": "check2", "name": "Has test scenario"},
            "result": {"status": "RUN_SUCCESS", "severity": 0, "message": "OK"},
        },
    },
}


def test_list_check_specs(ps):
    result = runner.invoke(app, ["project-standards", "list-check-specs"])
    assert result.exit_code == 0
    assert "project_standards_check_spec_project-standards_datasets" in result.output


def test_list_checks_json(ps):
    result = runner.invoke(
        app, ["--format", "json", "project-standards", "list-checks"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "check1"


def test_create_checks(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "create-checks",
            "--spec",
            "project_standards_check_spec_project-standards_datasets",
        ],
    )
    assert result.exit_code == 0
    ps.create_checks.assert_called_once_with(
        ["project_standards_check_spec_project-standards_datasets"]
    )
    assert "check1" in result.output


def test_create_scope(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "create-scope",
            "--name",
            "myscope",
            "--check",
            "check1",
            "--selection-method",
            "by_project",
            "--item",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    ps.create_scope.assert_called_once_with(
        "myscope",
        description="",
        checks=["check1"],
        selection_method="BY_PROJECT",
        items=["PROJ1"],
    )


def test_create_scope_bad_selection_method(ps):
    result = runner.invoke(
        app,
        [
            "project-standards",
            "create-scope",
            "--name",
            "x",
            "--selection-method",
            "BY_MAGIC",
        ],
    )
    assert result.exit_code == 2
    assert "by_project" in result.output.lower()


def test_run_wait_shows_severity(ps, patch_client):
    proj = patch_client.get_project("PROJ1")
    future = MagicMock()
    future.wait_for_result.return_value = DSSProjectStandardsRunReport(
        patch_client, _RAW_REPORT
    )
    proj.start_run_project_standards_checks.return_value = future

    result = runner.invoke(app, ["project-standards", "run", "-P", "PROJ1"])
    assert result.exit_code == 0
    # Non-compliance is severity >= 1 while status stays RUN_SUCCESS.
    assert "RUN_SUCCESS" in result.output
    assert "MEDIUM" in result.output
    assert "non-compliant" in result.output
    proj.start_run_project_standards_checks.assert_called_once_with(check_ids=None)


def test_run_no_wait(ps, patch_client):
    proj = patch_client.get_project("PROJ1")
    future = MagicMock()
    future.job_id = "fut42"
    proj.start_run_project_standards_checks.return_value = future

    result = runner.invoke(
        app,
        [
            "project-standards",
            "run",
            "-P",
            "PROJ1",
            "--check-id",
            "check1",
            "--no-wait",
        ],
    )
    assert result.exit_code == 0
    future.wait_for_result.assert_not_called()
    proj.start_run_project_standards_checks.assert_called_once_with(
        check_ids=["check1"]
    )


def test_last_report(ps, patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.get_project_standards_last_report.return_value = DSSProjectStandardsRunReport(
        patch_client, _RAW_REPORT
    )
    result = runner.invoke(
        app, ["--format", "json", "project-standards", "last-report", "-P", "PROJ1"]
    )
    assert result.exit_code == 0
    # stdout only — the non-compliance summary goes to stderr.
    parsed = json.loads(result.stdout)
    by_id = {r["check_id"]: r for r in parsed}
    assert by_id["check1"]["severity"] == 3
    assert by_id["check1"]["status"] == "RUN_SUCCESS"
    assert by_id["check2"]["severity_category"] == ""


def test_last_report_none(ps, patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.get_project_standards_last_report.return_value = None
    result = runner.invoke(app, ["project-standards", "last-report", "-P", "PROJ1"])
    assert result.exit_code != 0
    assert "dku project-standards run" in result.output
