"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_quiet():
    """Reset output modes between tests so global CLI flags do not leak."""
    from dku_cli.output import set_error_format, set_quiet

    set_quiet(False)
    set_error_format("text")
    yield
    set_quiet(False)
    set_error_format("text")


@pytest.fixture
def mock_client():
    """Create a mock DSSClient with common methods."""
    client = MagicMock()

    # Auth info
    client.get_auth_info.return_value = {
        "authIdentifier": "testuser",
        "groups": ["admin", "data_team"],
    }
    general_settings = MagicMock()
    general_settings.get_raw.return_value = {"dssVersion": "14.0.2"}
    client.get_general_settings.return_value = general_settings

    # Instance info (correct way to get DSS version)
    instance_info = MagicMock()
    instance_info.raw = {"dssVersion": "14.0.2"}
    client.get_instance_info.return_value = instance_info
    client.host = "https://dss.example.com"

    # Projects
    client.list_project_keys.return_value = ["PROJ1", "PROJ2"]

    proj1 = MagicMock()
    proj1.get_metadata.return_value = {
        "label": "Project One",
        "shortDesc": "First project",
    }
    proj1.list_datasets.return_value = [
        {
            "name": "ds1",
            "type": "UploadedFiles",
            "schema": {"columns": [{"name": "col1", "type": "string"}]},
        },
    ]
    proj1.list_recipes.return_value = [
        {"name": "recipe1", "type": "python", "tags": ["etl"]},
    ]

    # Scenarios — list_scenarios returns dict-like items (DSSScenarioListItem)
    scen_item = MagicMock()
    scen_item.get.side_effect = lambda k, d="": {
        "id": "scen1",
        "name": "Build All",
        "active": True,
        "type": "step_based",
    }.get(k, d)
    proj1.list_scenarios.return_value = [scen_item]

    # Saved models
    proj1.list_saved_models.return_value = [
        {"id": "model1", "name": "My Model", "type": "PREDICTION"},
    ]

    # Managed folders
    proj1.list_managed_folders.return_value = [
        {"id": "folder1", "name": "Data Folder", "type": "Filesystem"},
    ]

    # Webapps
    proj1.list_webapps.return_value = [
        {"id": "webapp1", "name": "Dashboard", "type": "STANDARD"},
        {
            "id": "hub1",
            "name": "Agent Hub - Main",
            "type": "webapp_agent-hub_agent-hub",
        },
    ]

    # LLMs
    proj1.list_llms.return_value = [
        {"id": "llm1", "type": "openai", "description": "GPT-4"},
    ]

    # Macros — real API returns runnableType + meta.label + ownerPluginId
    proj1.list_macros.return_value = [
        {
            "runnableType": "pyrunnable_test_run-macro",
            "ownerPluginId": "test-plugin",
            "meta": {"label": "My Macro"},
        },
    ]

    # Project Git
    git_mock = MagicMock()
    git_mock.get_status.return_value = {
        "currentBranch": "master",
        "clean": True,
        "hasUncommittedChanges": False,
        "added": [],
        "changed": [],
        "removed": [],
        "modified": [],
        "untracked": [],
        "conflicting": [],
    }
    git_mock.log.return_value = {
        "entries": [
            {
                "commitId": "abc123def456",
                "message": "Initial commit",
                "author": "testuser",
                "date": 1711900800000,
            }
        ],
        "nextCommit": None,
    }
    git_mock.diff.return_value = {
        "addedLines": 10,
        "removedLines": 5,
        "changedFiles": 2,
        "entries": [],
    }
    git_mock.commit.return_value = None
    git_mock.pull.return_value = {
        "success": True,
        "logs": [],
        "output": "Already up to date",
    }
    git_mock.push.return_value = {"success": True, "logs": [], "output": "ok"}
    git_mock.fetch.return_value = {"success": True, "logs": [], "output": "ok"}
    git_mock.list_branches.return_value = ["master", "feature/test"]
    git_mock.create_branch.return_value = {
        "success": True,
        "output": "Created branch",
    }
    git_mock.delete_branch.return_value = None
    git_mock.switch.return_value = {
        "success": True,
        "messages": [],
        "output": "Switched",
    }
    git_mock.list_tags.return_value = [
        {
            "name": "refs/tags/v1.0",
            "shortName": "v1.0",
            "commit": "abc123def456",
            "annotations": "",
            "readOnly": False,
        }
    ]
    git_mock.create_tag.return_value = None
    git_mock.get_remote.return_value = "https://github.com/example/project.git"
    git_mock.set_remote.return_value = None
    proj1.get_project_git.return_value = git_mock

    # Library mock — mimics DSSLibrary/DSSLibraryFile/DSSLibraryFolder
    library_mock = MagicMock()

    # list() returns DSSLibraryItem-like objects with .path property
    lib_item1 = MagicMock()
    lib_item1.path = "python/mylib/__init__.py"
    lib_item2 = MagicMock()
    lib_item2.path = "python/mylib/utils.py"
    library_mock.list.return_value = [lib_item1, lib_item2]

    # get_file() returns DSSLibraryFile with .read()/.write()/.delete()
    lib_file_mock = MagicMock()
    lib_file_mock.read.return_value = b"# utils.py\ndef transform(df):\n    return df"
    lib_file_mock.write.return_value = None
    lib_file_mock.delete.return_value = None
    library_mock.get_file.return_value = lib_file_mock

    # add_file() — Real dataikuapi returns None
    library_mock.add_file.return_value = None  # Real dataikuapi returns None

    # get_folder()/add_folder() return DSSLibraryFolder
    lib_folder_mock = MagicMock()
    lib_folder_mock.list.return_value = [lib_item1, lib_item2]
    lib_folder_mock.add_file.return_value = None  # Real dataikuapi returns None
    lib_folder_mock.add_folder.return_value = lib_folder_mock
    lib_folder_mock.get_folder.return_value = lib_folder_mock
    library_mock.get_folder.return_value = lib_folder_mock
    library_mock.add_folder.return_value = lib_folder_mock

    proj1.get_library.return_value = library_mock

    # Flow — real API returns DSSProjectFlowGraph with .nodes and .data attrs
    flow_mock = MagicMock()
    graph_mock = MagicMock()
    graph_mock.nodes = {
        "ds1": {
            "type": "COMPUTABLE_DATASET",
            "subType": "",
            "ref": "ds1",
            "successors": ["recipe1"],
        },
        "recipe1": {
            "type": "RUNNABLE_RECIPE",
            "subType": "python",
            "ref": "recipe1",
            "successors": [],
        },
    }
    graph_mock.data = {"nodes": graph_mock.nodes}
    graph_mock.get_successors.side_effect = AttributeError("not implemented")
    flow_mock.get_graph.return_value = graph_mock

    # Flow zones
    zone_mock = MagicMock()
    zone_mock.id = "zone1"
    zone_mock.name = "Default"
    # Zone settings mock for set-zone command
    zone_settings_mock = MagicMock()
    zone_settings_mock.name = "Default"
    zone_settings_mock.color = "#2ab1ac"
    zone_settings_mock.save.return_value = None
    zone_mock.get_settings.return_value = zone_settings_mock

    zone2_mock = MagicMock()
    zone2_mock.id = "XjxKvHzB"
    zone2_mock.name = "Processing"
    zone2_settings_mock = MagicMock()
    zone2_settings_mock.name = "Processing"
    zone2_settings_mock.color = "#FF5500"
    zone2_settings_mock.save.return_value = None
    zone2_mock.get_settings.return_value = zone2_settings_mock
    flow_mock.list_zones.return_value = [zone_mock, zone2_mock]
    flow_mock.create_zone.return_value = zone_mock

    # get_zone() resolves by ID
    def _get_zone(zone_id):
        zones = {"zone1": zone_mock, "XjxKvHzB": zone2_mock}
        if zone_id in zones:
            return zones[zone_id]
        raise Exception(f"NotFoundException: Zone {zone_id} does not exist")

    flow_mock.get_zone.side_effect = _get_zone

    # Flow schema propagation — uses new_schema_propagation(dataset_name) builder
    propagation_builder = MagicMock()
    propagation_builder.set_auto_rebuild.return_value = None
    propagation_builder.stop_at.return_value = None
    propagation_builder.mark_recipe_as_ok.return_value = None
    propagation_builder.start.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    flow_mock.new_schema_propagation.return_value = propagation_builder

    # Flow consistency check tool
    flow_tool_mock = MagicMock()
    flow_tool_mock.update.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"status": "OK"})
    )
    flow_tool_mock.get_state.return_value = {"status": "OK", "issues": []}
    flow_tool_mock.stop.return_value = None
    flow_mock.start_tool.return_value = flow_tool_mock

    proj1.get_flow.return_value = flow_mock

    # Project Git
    git_mock = MagicMock()
    git_mock.get_status.return_value = {
        "currentBranch": "master",
        "clean": True,
        "hasUncommittedChanges": False,
        "added": [],
        "changed": [],
        "removed": [],
        "modified": [],
        "untracked": [],
        "conflicting": [],
    }
    git_mock.log.return_value = {
        "entries": [
            {
                "commitId": "abc123def456",
                "message": "Initial commit",
                "author": "testuser",
                "date": 1711900800000,
            }
        ],
        "nextCommit": None,
    }
    git_mock.diff.return_value = {
        "addedLines": 10,
        "removedLines": 5,
        "changedFiles": 2,
        "entries": [],
    }
    git_mock.commit.return_value = None
    git_mock.pull.return_value = {
        "success": True,
        "logs": [],
        "output": "Already up to date",
    }
    git_mock.push.return_value = {"success": True, "logs": [], "output": "ok"}
    git_mock.fetch.return_value = {"success": True, "logs": [], "output": "ok"}
    git_mock.list_branches.return_value = ["master", "feature/test"]
    git_mock.create_branch.return_value = {
        "success": True,
        "output": "Created branch",
    }
    git_mock.delete_branch.return_value = None
    git_mock.switch.return_value = {
        "success": True,
        "messages": [],
        "output": "Switched",
    }
    git_mock.list_tags.return_value = [
        {
            "name": "refs/tags/v1.0",
            "shortName": "v1.0",
            "commit": "abc123def456",
            "annotations": "",
            "readOnly": False,
        }
    ]
    git_mock.create_tag.return_value = None
    git_mock.get_remote.return_value = "https://github.com/example/project.git"
    git_mock.set_remote.return_value = None
    proj1.get_project_git.return_value = git_mock

    # Recipe mock — settings uses get_recipe_raw_definition() and get_flat_input/output_refs()
    recipe_mock = MagicMock()
    recipe_settings = MagicMock()
    recipe_settings.get_recipe_raw_definition.return_value = {
        "type": "python",
        "name": "recipe1",
    }
    recipe_settings.get_flat_input_refs.return_value = ["input_ds"]
    recipe_settings.get_flat_output_refs.return_value = ["output_ds"]
    recipe_mock.get_settings.return_value = recipe_settings
    recipe_job = MagicMock()
    recipe_job.id = "job_recipe_1"
    recipe_job.get_status.return_value = {"baseStatus": {"state": "DONE"}}
    recipe_mock.run.return_value = recipe_job
    recipe_mock.delete.return_value = None
    recipe_mock.rename.return_value = None

    # Recipe status mock — get_status() returns DSSRecipeStatus-like object
    recipe_status_mock = MagicMock()
    recipe_status_mock.data = {
        "selectedEngine": {"type": "DSS"},
        "engines": [{"type": "DSS"}, {"type": "SPARK"}],
        "allMessagesForFrontend": {
            "maxSeverity": "SUCCESS",
            "messages": [
                {
                    "severity": "SUCCESS",
                    "isFatal": False,
                    "code": "recipe-check-ok",
                    "title": "Recipe is valid",
                    "message": "All checks passed",
                    "details": "",
                },
            ],
        },
    }
    recipe_status_mock.get_selected_engine_details.return_value = {"type": "DSS"}
    recipe_status_mock.get_status_severity.return_value = "SUCCESS"
    recipe_status_mock.get_status_messages.return_value = [
        {
            "severity": "SUCCESS",
            "isFatal": False,
            "code": "recipe-check-ok",
            "title": "Recipe is valid",
            "message": "All checks passed",
            "details": "",
        },
    ]
    recipe_mock.get_status.return_value = recipe_status_mock
    recipe_settings.set_payload.return_value = None
    recipe_settings.get_payload.return_value = "# Python code\nimport dataiku"
    recipe_settings.save.return_value = None
    recipe_settings.add_input.return_value = None
    recipe_settings.add_output.return_value = None
    # Recipe schema updates mock — compute_schema_updates() returns RequiredSchemaUpdates
    schema_updates_mock = MagicMock()
    schema_updates_mock.any_action_required.return_value = False
    schema_updates_mock.data = {
        "totalIncompatibilities": 0,
        "computables": [
            {
                "datasetName": "output_ds",
                "type": "DATASET",
                "newSchema": {"columns": [{"name": "col1", "type": "string"}]},
                "schemaChanged": False,
            }
        ],
    }
    schema_updates_mock.apply.return_value = [{"status": "ok"}]
    recipe_mock.compute_schema_updates.return_value = schema_updates_mock

    proj1.get_recipe.return_value = recipe_mock

    # Recipe builder mock for new_recipe()
    recipe_builder = MagicMock()
    recipe_builder.with_input.return_value = recipe_builder
    recipe_builder.with_existing_output.return_value = recipe_builder
    recipe_builder.with_output.return_value = recipe_builder
    recipe_builder.with_output_knowledge_bank.return_value = recipe_builder
    recipe_builder.with_output_metrics.return_value = recipe_builder
    recipe_builder.with_output_evaluation_store.return_value = recipe_builder
    recipe_builder.with_vlm.return_value = recipe_builder
    recipe_builder.build.return_value = recipe_mock
    recipe_builder.create.return_value = recipe_mock
    proj1.new_recipe.return_value = recipe_builder

    # obj_payload for GenAI recipe post-creation settings
    recipe_settings.obj_payload = {}
    # Provide raw_params fallback for _get_recipe_payload (obj_payload may be read-only in real API)
    recipe_settings.raw_params = {"payload": {}}

    # Dataset mocks — iter_rows returns lists (not dicts)
    dataset_mock = MagicMock()
    dataset_mock.get_definition.return_value = {
        "type": "UploadedFiles",
        "managed": True,
        "params": {"uploadConnection": "filesystem_managed"},
        "formatType": "csv",
        "tags": ["test"],
        "schema": {
            "columns": [
                {"name": "col1", "type": "string"},
                {"name": "col2", "type": "int"},
            ]
        },
    }
    dataset_mock.iter_rows.return_value = iter(
        [
            ["a", "1"],
            ["b", "2"],
        ]
    )
    build_job = MagicMock()
    build_job.id = "job_build_1"
    build_job.get_status.return_value = {"baseStatus": {"state": "DONE"}}
    dataset_mock.build.return_value = build_job
    dataset_mock.delete.return_value = None
    dataset_mock.clear.return_value = None
    dataset_mock.set_definition.return_value = None
    dataset_mock.uploaded_add_file.return_value = None
    dataset_mock.rename.return_value = None
    dataset_mock.copy_to.return_value = None
    dataset_mock.list_partitions.return_value = ["2026-01-01", "2026-01-02"]

    # Dataset metadata (description, tags — separate from definition)
    dataset_mock.get_metadata.return_value = {
        "label": "ds1",
        "description": "",
        "shortDesc": "",
        "tags": [],
    }
    dataset_mock.set_metadata.return_value = None
    dataset_mock.exists.return_value = True
    dataset_mock.get_usages.return_value = [
        {
            "type": "RECIPE_INPUT",
            "objectId": "compute_output",
            "objectProjectKey": "PROJ1",
        },
        {"type": "ANALYSIS", "objectId": "analysis_1", "objectProjectKey": "PROJ1"},
    ]
    dataset_mock.get_column_lineage.return_value = [
        {
            "inputDataset": "PROJ1.raw_input",
            "inputColumn": "revenue_raw",
            "outputDataset": "PROJ1.ds1",
            "outputColumn": "revenue",
        },
    ]
    dataset_mock.generate_ai_description.return_value = {
        "dataset": {"description": "Customer transactions dataset"},
        "columns": [
            {"name": "col1", "description": "First column identifier"},
            {"name": "col2", "description": "Numeric value"},
        ],
    }

    # autodetect_settings returns a DSSDatasetSettings-like object
    autodetect_result = MagicMock()
    autodetect_result.get_raw.return_value = {
        "formatType": "csv",
        "formatParams": {"style": "excel", "separator": ","},
        "schema": {
            "columns": [
                {"name": "col1", "type": "string"},
                {"name": "col2", "type": "int"},
            ]
        },
    }
    autodetect_result.save.return_value = None
    dataset_mock.autodetect_settings.return_value = autodetect_result

    # Dataset info mock (get_info returns DSSDatasetInfo-like object)
    ds_info_mock = MagicMock()
    ds_info_mock.get_raw.return_value = {
        "lastBuild": {
            "buildEndTime": 1712000000000,
            "buildStartTime": 1711999900000,
            "buildSuccess": True,
        }
    }
    dataset_mock.get_info.return_value = ds_info_mock

    # Dataset metrics mock (get_last_metric_values returns ComputedMetrics-like)
    ds_metrics_mock = MagicMock()
    ds_metrics_mock.get_all_ids.return_value = [
        "records:COUNT_RECORDS",
        "basic:SIZE",
        "basic:COUNT_FILES",
    ]

    def _get_metric_value(metric_id):
        return {
            "records:COUNT_RECORDS": 15000,
            "basic:SIZE": 2500000,
            "basic:COUNT_FILES": 3,
        }.get(metric_id, 0)

    ds_metrics_mock.get_global_value.side_effect = _get_metric_value
    dataset_mock.get_last_metric_values.return_value = ds_metrics_mock

    # Data Quality mocks
    dq_ruleset = MagicMock()

    dq_rule1_raw = {
        "id": "rule1",
        "displayName": "Record count check",
        "type": "RecordCountInRangeRule",
        "enabled": True,
        "softMinimum": 10,
        "softMinimumEnabled": True,
    }
    dq_rule2_raw = {
        "id": "rule2",
        "displayName": "Country not empty",
        "type": "ColumnNotEmptyRule",
        "enabled": True,
        "column": "CountryISO",
    }

    dq_rule_obj1 = MagicMock()
    dq_rule_obj1.id = "rule1"
    dq_rule_obj1.name = "Record count check"
    dq_rule_obj1.get_raw.return_value = dq_rule1_raw
    dq_rule_obj1.delete.return_value = None
    dq_rule_obj1.compute.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"status": "OK"})
    )

    dq_rule_obj2 = MagicMock()
    dq_rule_obj2.id = "rule2"
    dq_rule_obj2.name = "Country not empty"
    dq_rule_obj2.get_raw.return_value = dq_rule2_raw
    dq_rule_obj2.delete.return_value = None

    def _dq_list_rules(as_type="objects"):
        if as_type == "dict":
            return [dq_rule1_raw, dq_rule2_raw]
        return [dq_rule_obj1, dq_rule_obj2]

    dq_ruleset.list_rules.side_effect = _dq_list_rules

    new_dq_rule = MagicMock()
    new_dq_rule.id = "new_rule_1"
    new_dq_rule.name = "New Rule"
    new_dq_rule.get_raw.return_value = {
        "id": "new_rule_1",
        "displayName": "New Rule",
        "type": "RecordCountInRangeRule",
    }
    dq_ruleset.create_rule.return_value = new_dq_rule

    dq_ruleset.compute_rules.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"status": "OK"})
    )
    dq_ruleset.get_status.return_value = {"status": "OK", "outcome": "OK"}

    dq_result1 = MagicMock()
    dq_result1.id = "rule1"
    dq_result1.name = "Record count check"
    dq_result1.outcome = "OK"
    dq_result1.message = "Record count: 79 >= 10"
    dq_result1.compute_date = "2026-03-27T00:00:00"
    dq_result1.run_origin = "MANUAL"
    dq_result1.partition = "NP"
    dq_result1.get_raw.return_value = {
        "id": "rule1",
        "name": "Record count check",
        "outcome": "OK",
        "message": "Record count: 79 >= 10",
        "computeDate": "2026-03-27T00:00:00",
        "runOrigin": "MANUAL",
        "partition": "NP",
    }
    dq_ruleset.get_last_rules_results.return_value = [dq_result1]

    dataset_mock.get_data_quality_rules.return_value = dq_ruleset

    # Project-level DQ status
    proj1.get_data_quality_status.return_value = {
        "ds1": {"status": "OK", "lastCheck": "2026-03-27"},
    }

    proj1.get_dataset.return_value = dataset_mock

    # create_dataset returns a dataset mock
    proj1.create_dataset.return_value = dataset_mock

    managed_dataset_builder = MagicMock()
    managed_dataset_builder.with_store_into.return_value = managed_dataset_builder
    managed_dataset_builder.create.return_value = dataset_mock
    proj1.new_managed_dataset.return_value = managed_dataset_builder

    # Connection schema/table discovery mocks (project-level)
    proj1.list_sql_schemas.return_value = ["public", "analytics", "staging"]
    proj1.list_iceberg_namespaces.return_value = ["default", "production"]
    proj1.list_sql_tables.return_value = [
        {"schema": "public", "table": "customers"},
        {"schema": "public", "table": "orders"},
        {"schema": "analytics", "table": "revenue_daily"},
    ]
    proj1.list_iceberg_tables.return_value = [
        {"namespace": "default", "table": "events"},
        {"namespace": "default", "table": "sessions"},
    ]

    # Scenario create mock
    new_scenario_mock = MagicMock()
    new_scenario_mock.id = "new_scen"
    proj1.create_scenario.return_value = new_scenario_mock

    # Scenario run/abort/status/delete/definition mocks
    scenario_mock = MagicMock()
    # Real DSSTriggerFire may not have wait_for_result() — simulate that
    trigger_fire_mock = MagicMock(spec=[])  # empty spec = no auto-created attrs
    scenario_mock.run.return_value = trigger_fire_mock
    scenario_mock.abort.return_value = None
    scenario_mock.delete.return_value = None

    # Real dataikuapi returns a plain dict from get_definition(), not an object with .get_raw()
    scenario_mock.get_definition.return_value = {
        "type": "step_based",
        "name": "Build All",
        "description": "",
        "shortDesc": "",
        "tags": [],
        "params": {},
    }
    scenario_mock.set_definition.return_value = None

    # Scenario settings mock (for trigger commands)
    # raw_triggers returns a mutable reference, matching dataikuapi behavior
    scenario_triggers = [
        {
            "active": True,
            "type": "temporal",
            "params": {
                "frequency": "Daily",
                "hour": 2,
                "minute": 0,
                "repeatFrequency": 1,
                "timezone": "SERVER",
            },
        },
    ]
    scenario_settings_mock = MagicMock()
    type(scenario_settings_mock).raw_triggers = property(lambda self: scenario_triggers)
    scenario_settings_mock.save.return_value = None
    scenario_mock.get_settings.return_value = scenario_settings_mock

    # get_last_runs returns DSSScenarioRun objects with properties
    run_mock = MagicMock()
    run_mock.id = "run1"
    run_mock.start_time = "2025-01-01T00:00:00"
    run_mock.outcome = "SUCCESS"
    run_mock.trigger = {"type": "manual"}
    run_mock.get_info.return_value = {
        "id": "run1",
        "state": "SUCCESS",
        "start": "2025-01-01T00:00:00",
    }
    scenario_mock.get_last_runs.return_value = [run_mock]
    scenario_mock.get_last_finished_run.return_value = run_mock
    proj1.get_scenario.return_value = scenario_mock

    # Job mocks
    # list_jobs() returns top-level fields (NOT nested under baseStatus).
    # baseStatus wrapper is only from get_status() on a single job.
    proj1.list_jobs.return_value = [
        {
            "def": {"id": "job1", "initiator": "testuser"},
            "state": "DONE",
            "startTime": "2025-01-01T00:00:00",
            "endTime": "2025-01-01T00:01:00",
        },
    ]
    job_mock = MagicMock()
    job_mock.get_status.return_value = {
        "baseStatus": {
            "def": {"id": "job1", "initiator": "testuser"},
            "state": "DONE",
            "timing": {
                "startTime": "2025-01-01T00:00:00",
                "endTime": "2025-01-01T00:01:00",
            },
        }
    }
    job_mock.get_log.return_value = "Log line 1\nLog line 2"
    job_mock.abort.return_value = None
    proj1.get_job.return_value = job_mock

    # Job builder mock for new_job() — used by dku job run, dataset build --type, recipe run --type
    job_builder_mock = MagicMock()
    job_builder_mock.with_output.return_value = job_builder_mock
    job_builder_mock.with_auto_update_schema_before_each_recipe_run.return_value = (
        job_builder_mock
    )
    job_builder_mock.with_refresh_metastore.return_value = job_builder_mock
    started_job = MagicMock()
    started_job.id = "job_run_1"
    started_job.get_status.return_value = {"baseStatus": {"state": "DONE"}}
    job_builder_mock.start.return_value = started_job
    job_builder_mock.start_and_wait.return_value = started_job
    proj1.new_job.return_value = job_builder_mock

    # Webapp mock — get_state returns object with .running property
    webapp_mock = MagicMock()
    webapp_state = MagicMock()
    webapp_state.running = True
    webapp_mock.get_state.return_value = webapp_state
    webapp_mock.start_or_restart_backend.return_value = None
    webapp_mock.stop_backend.return_value = None
    webapp_settings = MagicMock()
    webapp_settings.get_raw.return_value = {
        "id": "webapp1",
        "name": "Dashboard",
        "type": "STANDARD",
        "params": {
            "html": "<h1>Hello</h1>",
            "css": "h1 { color: blue; }",
            "js": "console.log('hello');",
            "python": "# backend code",
        },
    }
    webapp_settings.save.return_value = None
    webapp_mock.get_settings.return_value = webapp_settings

    # Agent Hub webapp mock
    hub_webapp = MagicMock()
    hub_settings = MagicMock()
    hub_settings.get_raw.return_value = {
        "type": "webapp_agent-hub_agent-hub",
        "id": "hub1",
        "projectKey": "PROJ1",
        "config": {
            "default_llm_id": "openai:conn:gpt-4o",
            "globalSystemPrompt": "",
            "enable_agents_as_tools": True,
            "projects_keys": ["PROJ1"],
            "agents_ids": ["PROJ1:agent:a1"],
            "tool_agent_configurations": [
                {
                    "agent_id": "PROJ1:agent:a1",
                    "tool_agent_display_name": "Sales Agent",
                    "tool_agent_description": "Handles sales queries",
                    "agent_system_instructions": "",
                    "agent_example_queries": ["What are Q4 sales?"],
                    "enable_stories": False,
                },
            ],
            "augmented_llms_ids": [],
            "augmented_llms_configurations": [],
            "enable_quick_agents": True,
            "LLMs": [{"llm_id": "openai:conn:gpt-4o"}],
            "embedding_llm": "openai:conn:text-embedding-3-small",
            "tools": ["tool1"],
            "visualization_generation_mode": "AUTO",
            "logLevel": "INFO",
        },
    }
    hub_settings.save.return_value = None
    hub_webapp.get_settings.return_value = hub_settings
    hub_webapp.get_state.return_value = MagicMock(running=True)
    hub_webapp.start_or_restart_backend.return_value = MagicMock()
    hub_webapp.stop_backend.return_value = None

    # Route get_webapp by ID
    def _get_webapp(wid):
        if wid == "hub1":
            return hub_webapp
        return webapp_mock

    proj1.get_webapp.side_effect = _get_webapp

    # Dashboards
    proj1.list_dashboards.return_value = [
        {"id": "dashboard1", "name": "Sales Dashboard", "pages": [], "tags": []},
    ]
    dashboard_mock = MagicMock()
    dashboard_settings = MagicMock()
    dashboard_raw = {
        "id": "dashboard1",
        "name": "Sales Dashboard",
        "description": "",
        "shortDesc": "",
        "tags": [],
        "pages": [
            {
                "id": "page1",
                "title": "Overview",
                "grid": {"tiles": [{"tileType": "INSIGHT", "insightId": "i1"}]},
            }
        ],
    }
    dashboard_settings.get_raw.return_value = dashboard_raw
    dashboard_settings.save.return_value = None
    # DSSTaggableObjectSettings properties for set-metadata
    dashboard_settings.description = dashboard_raw.get("description", "")
    dashboard_settings.short_description = dashboard_raw.get("shortDesc", "")
    dashboard_settings.tags = dashboard_raw.get("tags", [])
    dashboard_mock.get_settings.return_value = dashboard_settings
    dashboard_mock.delete.return_value = None
    dashboard_mock.dashboard_id = "dashboard1"
    proj1.get_dashboard.return_value = dashboard_mock
    new_dashboard_mock = MagicMock()
    new_dashboard_mock.dashboard_id = "new_dashboard_1"
    proj1.create_dashboard.return_value = new_dashboard_mock

    # Insights
    proj1.list_insights.return_value = [
        {"id": "insight1", "name": "Sales Chart", "type": "chart"},
    ]
    insight_mock = MagicMock()
    insight_settings = MagicMock()
    insight_raw = {
        "id": "insight1",
        "name": "Sales Chart",
        "type": "chart",
        "description": "",
        "shortDesc": "",
        "tags": [],
        "params": {},
    }
    insight_settings.get_raw.return_value = insight_raw
    insight_settings.save.return_value = None
    # DSSTaggableObjectSettings properties for set-metadata
    insight_settings.description = insight_raw.get("description", "")
    insight_settings.short_description = insight_raw.get("shortDesc", "")
    insight_settings.tags = insight_raw.get("tags", [])
    insight_mock.get_settings.return_value = insight_settings
    insight_mock.delete.return_value = None
    proj1.get_insight.return_value = insight_mock
    new_insight_mock = MagicMock()
    new_insight_mock.insight_id = "new_insight_1"
    proj1.create_insight.return_value = new_insight_mock

    # Managed folder mock
    folder_mock = MagicMock()
    folder_mock.id = "folder1"
    folder_mock.list_contents.return_value = {
        "items": [
            {"path": "/data.csv", "size": 1024, "lastModified": 1700000000000},
        ]
    }
    folder_mock.put_file.return_value = None
    folder_mock.delete.return_value = None
    folder_mock.delete_file.return_value = None
    folder_mock.rename.return_value = None
    folder_settings = MagicMock()
    folder_settings.get_raw.return_value = {
        "id": "folder1",
        "name": "Data Folder",
        "description": "",
        "tags": [],
        "projectKey": "PROJ1",
        "type": "Filesystem",
        "params": {
            "connection": "filesystem_folders",
            "path": "/${projectKey}/${odbId}",
        },
    }
    # Folder definition (separate from settings) for set-metadata
    folder_mock.get_definition.return_value = {
        "id": "folder1",
        "name": "Data Folder",
        "description": "",
        "tags": [],
        "projectKey": "PROJ1",
        "type": "Filesystem",
    }
    folder_mock.set_definition.return_value = None
    folder_settings.save.return_value = None
    folder_mock.get_settings.return_value = folder_settings
    folder_dataset_mock = MagicMock()
    folder_mock.create_dataset_from_files.return_value = folder_dataset_mock
    proj1.get_managed_folder.return_value = folder_mock

    # Folder creation mock
    new_folder_mock = MagicMock()
    new_folder_mock.id = "aBcDeFgH"
    proj1.create_managed_folder.return_value = new_folder_mock

    # Saved model mock — uses get_settings().get_raw() and get_active_version()
    model_mock = MagicMock()
    model_settings = MagicMock()
    model_raw = {
        "name": "My Model",
        "type": "PREDICTION",
        "description": "",
        "shortDesc": "",
        "tags": [],
    }
    model_settings.get_raw.return_value = model_raw
    model_settings.save.return_value = None
    # DSSTaggableObjectSettings properties for set-metadata
    model_settings.description = model_raw.get("description", "")
    model_settings.short_description = model_raw.get("shortDesc", "")
    model_settings.tags = model_raw.get("tags", [])
    model_mock.get_settings.return_value = model_settings
    model_mock.get_active_version.return_value = {"id": "v1"}
    model_mock.list_versions.return_value = [
        {"id": "v1", "active": True, "snippet": {"algorithm": "RandomForest"}},
        {"id": "v2", "active": False, "snippet": {"algorithm": "XGBoost"}},
    ]
    model_mock.set_active_version.return_value = None
    model_mock.delete_versions.return_value = None
    version_details_mock = MagicMock()
    version_details_mock.get_performance_metrics.return_value = {
        "auc": 0.92,
        "accuracy": 0.88,
        "precision": 0.85,
        "recall": 0.91,
        "f1": 0.88,
    }
    model_mock.get_version_details.return_value = version_details_mock
    proj1.get_saved_model.return_value = model_mock

    # LLM mock
    llm_mock = MagicMock()
    completion_mock = MagicMock()
    completion_mock.with_message.return_value = completion_mock
    completion_mock.with_system_message.return_value = completion_mock
    llm_response = MagicMock()
    llm_response.text = "Hello from LLM"
    llm_response.success = True
    llm_response.total_usage = {"totalTokens": 10}
    completion_mock.execute.return_value = llm_response
    llm_mock.new_completion.return_value = completion_mock

    # LLM embeddings
    embeddings_mock = MagicMock()
    embeddings_mock.add_text.return_value = embeddings_mock
    embeddings_response = MagicMock()
    embeddings_response.get_embeddings.return_value = [[0.1, 0.2, 0.3]]
    embeddings_mock.execute.return_value = embeddings_response
    llm_mock.new_embeddings.return_value = embeddings_mock

    embedding_llm_mock = MagicMock()
    embedding_embeddings_mock = MagicMock()
    embedding_embeddings_mock.add_text.return_value = embedding_embeddings_mock
    embedding_embeddings_response = MagicMock()
    embedding_embeddings_response.get_embeddings.return_value = [[0.4, 0.5, 0.6]]
    embedding_embeddings_mock.execute.return_value = embedding_embeddings_response
    embedding_llm_mock.new_embeddings.return_value = embedding_embeddings_mock

    def _list_llms(purpose="GENERIC_COMPLETION", as_type="listitems"):
        by_purpose = {
            "GENERIC_COMPLETION": [
                {"id": "llm1", "type": "CHAT", "description": "Test LLM"},
                {
                    "id": "azureopenai:Azure_AI_Connection:4o",
                    "type": "CHAT",
                    "description": "Azure OpenAI 4o",
                },
            ],
            "TEXT_EMBEDDING_EXTRACTION": [
                {
                    "id": "embedding1",
                    "type": "EMBEDDINGS",
                    "description": "Embedding model",
                },
            ],
        }
        return by_purpose.get(purpose, [])

    def _get_llm(llm_id):
        llms = {
            "llm1": llm_mock,
            "embedding1": embedding_llm_mock,
            "azureopenai:Azure_AI_Connection:4o": llm_mock,
            "agent:agent1": llm_mock,
            "agent:agent_blocks": llm_mock,
            "agent:structured_agent": llm_mock,
        }
        return llms.get(llm_id, llm_mock)

    proj1.list_llms.side_effect = _list_llms
    proj1.get_llm.return_value = llm_mock
    proj1.get_llm.side_effect = _get_llm

    # Macro mock
    macro_mock = MagicMock()
    macro_mock.run.return_value = {"status": "ok"}
    proj1.get_macro.return_value = macro_mock

    # Bundles
    proj1.list_exported_bundles.return_value = [{"id": "v1"}, {"id": "v2"}]
    proj1.export_bundle.return_value = None
    proj1.download_exported_bundle_archive_to_file.return_value = None
    proj1.import_bundle_from_archive.return_value = None
    proj1.activate_bundle.return_value = None
    proj1.preload_bundle.return_value = None

    # API Services
    proj1.list_api_services.return_value = [{"id": "myservice", "name": "My Service"}]
    api_service_mock = MagicMock()
    api_service_settings = MagicMock()
    api_service_settings.get_raw.return_value = {"id": "myservice", "endpoints": []}
    api_service_mock.get_settings.return_value = api_service_settings
    api_service_mock.create_package.return_value = None
    api_service_mock.list_packages.return_value = [
        {"id": "pkg1", "createdOn": "2025-01-01"}
    ]
    proj1.get_api_service.return_value = api_service_mock
    proj1.create_api_service.return_value = api_service_mock

    # Project CRUD
    client.create_project.return_value = MagicMock()
    proj1.delete.return_value = None
    proj1.duplicate.return_value = MagicMock()

    # Project variables
    proj1.get_variables.return_value = {
        "standard": {"key1": "val1"},
        "local": {"local1": "lval1"},
    }
    proj1.set_variables.return_value = None

    # Project permissions
    proj1.get_permissions.return_value = {
        "permissions": [{"user": "admin", "admin": True}],
    }
    proj1.set_permissions.return_value = None

    # Agents — mimics real DSSAgentSettings structure
    proj1.list_agents.return_value = [{"id": "agent1", "name": "My Agent"}]
    agent_mock = MagicMock()

    # Build version settings structure matching dataikuapi's DSSAgentVersionSettings
    agent_version_data = {
        "versionId": "v1",
        "toolsUsingAgentSettings": {
            "llmId": "llm1",
            "tools": [{"toolRef": "existing_tool"}],
        },
    }
    agent_raw = {
        "projectKey": "PROJ1",
        "id": "agent1",
        "name": "My Agent",
        "type": "TOOLS_USING_AGENT",
        "activeVersion": "v1",
        "versions": [agent_version_data],
    }

    agent_settings = MagicMock()
    agent_settings.get_raw.return_value = agent_raw
    agent_settings.active_version = "v1"
    agent_settings.type = "TOOLS_USING_AGENT"
    agent_settings.get_version_ids.return_value = ["v1"]
    agent_settings.save.return_value = None
    # DSSTaggableObjectSettings properties for set-metadata
    agent_settings.description = ""
    agent_settings.short_description = ""
    agent_settings.tags = []

    # Build a version settings mock that behaves like DSSAgentVersionSettings
    agent_ver_settings = MagicMock()
    agent_ver_settings.get_raw.return_value = agent_version_data
    agent_ver_settings.llm_id = agent_version_data["toolsUsingAgentSettings"]["llmId"]
    agent_ver_settings.tools = agent_version_data["toolsUsingAgentSettings"]["tools"]

    def _set_llm_id(value):
        agent_version_data["toolsUsingAgentSettings"]["llmId"] = value

    type(agent_ver_settings).llm_id = property(
        lambda self: agent_version_data["toolsUsingAgentSettings"]["llmId"],
        lambda self, v: _set_llm_id(v),
    )

    def _add_tool(tool):
        tool_dict = {"toolRef": tool} if isinstance(tool, str) else tool
        agent_version_data["toolsUsingAgentSettings"]["tools"].append(tool_dict)

    agent_ver_settings.add_tool = _add_tool

    agent_settings.get_version_settings.return_value = agent_ver_settings

    agent_mock.get_settings.return_value = agent_settings
    agent_mock.status.return_value = {"state": "RUNNING"}
    agent_mock.delete.return_value = None
    agent_mock.wake_up.return_value = None
    agent_mock.shutdown.return_value = None
    agent_mock.id = "agent1"
    agent_mock.as_llm.return_value = llm_mock

    # Agent with BLOCKS_GRAPH mode (for agent-block commands)
    agent_blocks_mock = MagicMock()
    agent_blocks_version_data = {
        "versionId": "v1",
        "toolsUsingAgentSettings": {
            "mode": "BLOCKS_GRAPH",
            "startingBlockId": "init_state",
            "blocks": [
                {
                    "type": "SET_STATE_ENTRIES",
                    "id": "init_state",
                    "entriesToSet": [
                        {"secret": False, "key": "status", "value": "started"}
                    ],
                    "nextBlock": "classify",
                },
                {
                    "type": "LLM_REQUEST",
                    "id": "classify",
                    "llmId": "llm1",
                    "outputMode": "SAVE_TO_STATE",
                    "outputStateKey": "intent",
                    "nextBlock": "emit_result",
                },
                {
                    "type": "EMIT_OUTPUT",
                    "id": "emit_result",
                    "templateType": "CEL_EXPANSION",
                    "template": "Done",
                    "addToMessages": True,
                },
            ],
            "tools": [],
        },
    }
    agent_blocks_raw = {
        "projectKey": "PROJ1",
        "id": "agent_blocks",
        "name": "Block Agent",
        "type": "TOOLS_USING_AGENT",
        "activeVersion": "v1",
        "versions": [agent_blocks_version_data],
    }
    agent_blocks_settings = MagicMock()
    agent_blocks_settings.get_raw.return_value = agent_blocks_raw
    agent_blocks_settings.active_version = "v1"
    agent_blocks_settings.type = "TOOLS_USING_AGENT"
    agent_blocks_settings.get_version_ids.return_value = ["v1"]
    agent_blocks_settings.save.return_value = None
    agent_blocks_mock.get_settings.return_value = agent_blocks_settings
    agent_blocks_mock.status.return_value = {"state": "RUNNING"}
    agent_blocks_mock.delete.return_value = None
    agent_blocks_mock.id = "agent_blocks"

    # Structured Agent (DSS 14.5+ — structuredAgentSettings)
    structured_agent_mock = MagicMock()
    structured_agent_version_data = {
        "versionId": "v1",
        "structuredAgentSettings": {
            "mode": "BLOCKS_GRAPH",
            "startingBlockId": "main_loop",
            "blocks": [
                {
                    "type": "CORE_LOOP",
                    "id": "main_loop",
                    "defaultNextBlock": "output",
                    "tools": [],
                },
                {
                    "type": "GENERATE_OUTPUT",
                    "id": "output",
                    "template": "Done",
                },
            ],
            "tools": [],
        },
    }
    structured_agent_raw = {
        "projectKey": "PROJ1",
        "id": "structured_agent",
        "name": "Structured Agent",
        "type": "STRUCTURED_AGENT",
        "activeVersion": "v1",
        "versions": [structured_agent_version_data],
    }
    structured_agent_settings = MagicMock()
    structured_agent_settings.get_raw.return_value = structured_agent_raw
    structured_agent_settings.active_version = "v1"
    structured_agent_settings.type = "STRUCTURED_AGENT"
    structured_agent_settings.get_version_ids.return_value = ["v1"]
    structured_agent_settings.save.return_value = None

    structured_agent_ver_settings = MagicMock()
    structured_agent_ver_settings.get_raw.return_value = structured_agent_version_data

    # llm_id property raises ValueError for structured agents (no dataikuapi support)
    def _structured_set_llm_id(value):
        raise ValueError("Cannot set llm_id on structured agent via property")

    type(structured_agent_ver_settings).llm_id = property(
        lambda self: None,
        lambda self, v: _structured_set_llm_id(v),
    )

    # add_tool raises ValueError for structured agents
    def _structured_add_tool(tool):
        raise ValueError("Cannot add tool on structured agent via method")

    structured_agent_ver_settings.add_tool = _structured_add_tool

    structured_agent_settings.get_version_settings.return_value = (
        structured_agent_ver_settings
    )

    structured_agent_mock.get_settings.return_value = structured_agent_settings
    structured_agent_mock.status.return_value = {"state": "RUNNING"}
    structured_agent_mock.delete.return_value = None
    structured_agent_mock.wake_up.return_value = None
    structured_agent_mock.shutdown.return_value = None
    structured_agent_mock.id = "structured_agent"

    # Structured Agent with NO structuredAgentSettings initialized (newly created)
    structured_agent_empty_mock = MagicMock()
    structured_agent_empty_version_data = {"versionId": "v1"}
    structured_agent_empty_raw = {
        "projectKey": "PROJ1",
        "id": "structured_agent_empty",
        "name": "Empty Structured Agent",
        "type": "STRUCTURED_AGENT",
        "activeVersion": "v1",
        "versions": [structured_agent_empty_version_data],
    }
    structured_agent_empty_settings = MagicMock()
    structured_agent_empty_settings.get_raw.return_value = structured_agent_empty_raw
    structured_agent_empty_settings.active_version = "v1"
    structured_agent_empty_settings.type = "STRUCTURED_AGENT"
    structured_agent_empty_settings.get_version_ids.return_value = ["v1"]
    structured_agent_empty_settings.save.return_value = None
    structured_agent_empty_mock.get_settings.return_value = (
        structured_agent_empty_settings
    )
    structured_agent_empty_mock.status.return_value = {"state": "STOPPED"}
    structured_agent_empty_mock.id = "structured_agent_empty"

    # Include structured_agent and structured_agent_empty in list_agents
    proj1.list_agents.return_value = [
        {"id": "agent1", "name": "My Agent"},
        {"id": "agent_blocks", "name": "Block Agent"},
        {"id": "structured_agent", "name": "Structured Agent"},
        {"id": "structured_agent_empty", "name": "Empty Structured Agent"},
    ]

    # Route get_agent by agent_id
    def _get_agent(agent_id):
        if agent_id == "agent1":
            return agent_mock
        if agent_id == "agent_blocks":
            return agent_blocks_mock
        if agent_id == "structured_agent":
            return structured_agent_mock
        if agent_id == "structured_agent_empty":
            return structured_agent_empty_mock
        raise Exception(f"NotFoundException: Agent {agent_id} does not exist")

    proj1.get_agent.side_effect = _get_agent

    # create_agent returns agent with .id
    new_agent_mock = MagicMock()
    new_agent_mock.id = "new_agent_1"
    proj1.create_agent.return_value = new_agent_mock

    # Agent tools
    proj1.list_agent_tools.return_value = [
        {"id": "tool1", "name": "My Tool", "type": "DatasetRowLookup"}
    ]
    tool_mock = MagicMock()
    tool_raw = {
        "id": "tool1",
        "name": "My Tool",
        "type": "DatasetRowLookup",
        "params": {"retrievalMode": "SINGLE_RECORD", "maxRecords": 5},
    }
    tool_settings = MagicMock()
    tool_settings.get_raw.return_value = tool_raw
    tool_settings.params = tool_raw["params"]
    tool_settings.save.return_value = None
    tool_mock.get_settings.return_value = tool_settings
    tool_mock.run.return_value = {"result": "success", "output": "done"}
    tool_mock.delete.return_value = None
    tool_mock.id = "tool1"
    proj1.get_agent_tool.return_value = tool_mock

    # Agent tool creation — new_agent_tool() returns a builder with .create()
    new_tool_mock = MagicMock()
    new_tool_mock.id = "new_tool_1"
    new_tool_settings = MagicMock()
    new_tool_settings.params = {}
    new_tool_settings.save.return_value = None
    new_tool_mock.get_settings.return_value = new_tool_settings
    tool_builder = MagicMock()
    tool_builder.with_knowledge_bank.return_value = tool_builder
    tool_builder.create.return_value = new_tool_mock
    proj1.new_agent_tool.return_value = tool_builder

    # Agent reviews
    review_item = MagicMock()
    review_item.id = "review1"
    review_item.name = "Quality Check"
    review_item.data = {
        "id": "review1",
        "name": "Quality Check",
        "agentSmartId": "agent1",
        "owner": "testuser",
        "helperLLMId": "llm1",
        "traits": [],
    }
    proj1.list_agent_reviews.return_value = [review_item]

    review_mock = MagicMock()
    review_mock.id = "review1"
    review_mock.name = "Quality Check"
    review_mock.agent_id = "agent1"
    review_mock.helper_llm_id = "llm1"
    review_mock.data = {
        "id": "review1",
        "name": "Quality Check",
        "agentSmartId": "agent1",
        "owner": "testuser",
        "helperLLMId": "llm1",
        "traits": [],
    }
    review_mock.get_raw.return_value = review_mock.data
    review_mock.save.return_value = review_mock
    review_mock.delete.return_value = None
    review_mock.add_trait.return_value = None

    # Review tests
    review_test_mock = MagicMock()
    review_test_mock.id = "test1"
    review_test_mock.query = "What is 2+2?"
    review_test_mock.reference_answer = "4"
    review_test_mock.expectations = "Should be numeric"
    review_mock.list_tests.return_value = [review_test_mock]
    review_mock.create_test.return_value = review_test_mock
    review_mock.create_tests_from_dataset.return_value = {
        "createdTestIds": ["t1", "t2", "t3"],
        "error": None,
    }
    review_mock.export_tests_to_dataset.return_value = {
        "exportedTestCount": 3,
        "error": None,
    }

    # Review runs
    review_run_mock = MagicMock()
    review_run_mock.id = "run1"
    review_run_mock.name = "nightly-eval"
    review_run_mock.status = "COMPLETED"
    review_run_mock.agent_id = "agent1"
    review_mock.list_runs.return_value = [review_run_mock]
    review_mock.perform_run.return_value = review_run_mock
    review_mock.get_run.return_value = review_run_mock

    # Review results
    review_result_mock = MagicMock()
    review_result_mock.id = "result1"
    review_result_mock.test_id = "test1"
    review_result_mock.query = "What is 2+2?"
    review_result_mock.status = "PASSED"
    review_run_mock.list_results.return_value = [review_result_mock]

    def _get_agent_review(review_id):
        if review_id == "review1":
            return review_mock
        raise Exception(f"NotFoundException: Agent review {review_id} does not exist")

    proj1.get_agent_review.side_effect = _get_agent_review
    proj1.create_agent_review.return_value = review_mock

    # Code Studios
    cs_list_item = MagicMock()
    cs_list_item.id = "cs1"
    cs_list_item.name = "My Studio"
    cs_list_item.owner = "testuser"
    cs_list_item.template_id = "tpl1"
    cs_list_item.template_label = "Python Notebook"
    proj1.list_code_studios.return_value = [cs_list_item]

    cs_mock = MagicMock()
    cs_settings = MagicMock()
    cs_settings.get_raw.return_value = {
        "id": "cs1",
        "name": "My Studio",
        "templateId": "tpl1",
        "owner": "testuser",
    }
    cs_settings.id = "cs1"
    cs_settings.name = "My Studio"
    cs_settings.template_id = "tpl1"
    cs_settings.owner = "testuser"
    cs_mock.get_settings.return_value = cs_settings
    cs_status = MagicMock()
    cs_status.state = "STOPPED"
    cs_status.last_state_change = None
    cs_status.get_raw.return_value = {"state": "STOPPED"}
    cs_mock.get_status.return_value = cs_status
    cs_mock.restart.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    cs_mock.stop.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    cs_mock.delete.return_value = None
    cs_mock.change_owner.return_value = {"id": "cs1", "owner": "newuser"}
    cs_mock.id = "cs1"
    proj1.get_code_studio.return_value = cs_mock
    proj1.create_code_studio.return_value = cs_mock

    # Code Studio templates (client-level)
    cs_tpl = MagicMock()
    cs_tpl.id = "tpl1"
    cs_tpl.label = "Python Notebook"
    client.list_code_studio_templates.return_value = [cs_tpl]

    # API Deployer
    api_deployer_mock = MagicMock()
    api_deployer_mock.list_infras.return_value = [
        {"infraBasicInfo": {"id": "infra1", "type": "STATIC"}},
    ]
    api_deployer_mock.list_services.return_value = [
        {"serviceBasicInfo": {"id": "svc1"}},
    ]

    api_svc_handle = MagicMock()
    api_svc_settings = MagicMock()
    api_svc_settings.get_raw.return_value = {"id": "svc1"}
    api_svc_handle.get_settings.return_value = api_svc_settings
    api_deployer_mock.get_service.return_value = api_svc_handle

    api_deployer_mock.list_deployments.return_value = [
        {
            "deploymentBasicInfo": {
                "id": "dep1",
                "serviceId": "svc1",
                "infraId": "infra1",
            }
        },
    ]

    api_dep_handle = MagicMock()
    api_dep_settings = MagicMock()
    api_dep_settings.get_raw.return_value = {
        "id": "dep1",
        "serviceId": "svc1",
        "infraId": "infra1",
    }
    api_dep_handle.get_settings.return_value = api_dep_settings
    api_dep_handle.get_light_status.return_value = {"health": "HEALTHY"}
    api_dep_handle.start_update.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    api_dep_handle.delete.return_value = None
    api_deployer_mock.get_deployment.return_value = api_dep_handle
    api_deployer_mock.create_deployment.return_value = api_dep_handle

    client.get_apideployer.return_value = api_deployer_mock

    # Project Deployer
    proj_deployer_mock = MagicMock()
    proj_deployer_mock.list_infras.return_value = [
        {"infraBasicInfo": {"id": "auto_infra1", "type": "STATIC"}},
    ]
    proj_deployer_mock.list_projects.return_value = [
        {"projectBasicInfo": {"id": "dp1"}},
    ]
    proj_deployer_mock.list_deployments.return_value = [
        {
            "deploymentBasicInfo": {
                "id": "pdep1",
                "projectKey": "dp1",
                "infraId": "auto_infra1",
            }
        },
    ]

    proj_dep_handle = MagicMock()
    proj_dep_settings = MagicMock()
    proj_dep_settings.get_raw.return_value = {
        "id": "pdep1",
        "projectId": "dp1",
        "infraId": "auto_infra1",
    }
    proj_dep_handle.get_settings.return_value = proj_dep_settings
    proj_dep_handle.get_light_status.return_value = {"health": "HEALTHY"}
    proj_dep_handle.start_update.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    proj_dep_handle.delete.return_value = None
    proj_deployer_mock.get_deployment.return_value = proj_dep_handle
    proj_deployer_mock.create_deployment.return_value = proj_dep_handle

    client.get_projectdeployer.return_value = proj_deployer_mock

    # Notebooks
    jupyter_nb = MagicMock()
    jupyter_nb.name = "my_notebook"
    proj1.list_jupyter_notebooks.return_value = [jupyter_nb]

    sql_nb = MagicMock()
    sql_nb.name = "my_sql_notebook"
    sql_nb._data = {
        "id": "sql_nb1",
        "name": "my_sql_notebook",
        "connection": "postgres",
    }
    proj1.list_sql_notebooks.return_value = [sql_nb]

    nb_mock = MagicMock()
    nb_content = MagicMock()
    nb_content.get_raw.return_value = {"cells": [], "metadata": {}}
    nb_content.save.return_value = None
    nb_mock.get_content.return_value = nb_content
    nb_mock.get_sessions.return_value = []
    nb_mock.unload.return_value = {}
    nb_mock.delete.return_value = None
    nb_mock.clear_outputs.return_value = None
    nb_mock.name = "my_notebook"
    proj1.get_jupyter_notebook.return_value = nb_mock
    proj1.create_jupyter_notebook.return_value = nb_mock

    sql_nb_mock = MagicMock()
    sql_nb_content = MagicMock()
    sql_nb_content.get_raw.return_value = {"connection": "postgres", "cells": []}
    sql_nb_mock.get_content.return_value = sql_nb_content
    sql_history = MagicMock()
    sql_history.get_raw = MagicMock(return_value={"queries": []})
    sql_nb_mock.get_history.return_value = sql_history
    sql_nb_mock.delete.return_value = None
    proj1.get_sql_notebook.return_value = sql_nb_mock

    proj1.list_running_notebooks.return_value = [
        {
            "projectKey": "PROJ1",
            "name": "my_notebook",
            "kernelId": "k1",
            "sessionId": "s1",
        }
    ]

    # Discussions (on dataset_mock since it's most common)
    disc_mock = MagicMock()
    disc_metadata = {"id": "disc1", "topic": "Data quality issue"}
    disc_mock.get_metadata.return_value = disc_metadata
    disc_reply = MagicMock()
    disc_reply.get_text.return_value = "Fixed in v2"
    disc_reply.get_author.return_value = "admin"
    disc_mock.get_replies.return_value = [disc_reply]
    disc_mock.add_reply.return_value = None

    discussions_mock = MagicMock()
    discussions_mock.list_discussions.return_value = [disc_mock]
    discussions_mock.get_discussion.return_value = disc_mock
    discussions_mock.create_discussion.return_value = disc_mock

    dataset_mock.get_object_discussions.return_value = discussions_mock
    recipe_mock.get_object_discussions.return_value = discussions_mock

    # Knowledge banks
    proj1.list_knowledge_banks.return_value = [{"id": "kb1", "name": "My KB"}]
    kb_mock = MagicMock()
    kb_settings = MagicMock()
    kb_settings.get_raw.return_value = {"id": "kb1", "name": "My KB"}
    kb_mock.get_settings.return_value = kb_settings
    kb_mock.build.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    kb_mock.search.return_value = [{"content": "result1", "score": 0.95}]
    kb_mock.delete.return_value = None
    proj1.get_knowledge_bank.return_value = kb_mock
    proj1.create_knowledge_bank.return_value = kb_mock

    # Semantic models
    proj1.list_semantic_models.return_value = [
        {"id": "sm1", "name": "My Semantic Model", "projectKey": "PROJ1", "tags": []},
    ]
    sm_mock = MagicMock()
    sm_mock.id = "sm1"
    sm_mock.semantic_model_id = "sm1"
    sm_mock._get_definition.return_value = {
        "id": "sm1",
        "name": "My Semantic Model",
        "activeVersionId": "v1",
        "versions": [
            {
                "id": "v1",
                "description": "Initial version",
                "entities": [],
                "relationships": [],
            },
        ],
    }
    sm_mock.get_active_version_id.return_value = "v1"
    sm_mock.list_versions_ids.return_value = ["v1"]
    sm_mock.delete.return_value = None
    sm_mock.set_active_version_id.return_value = None

    sm_version_mock = MagicMock()
    sm_version_settings = MagicMock()
    sm_version_settings.get_raw.return_value = {
        "id": "v1",
        "description": "Initial version",
        "entities": [],
        "relationships": [],
        "goldenQueries": [],
        "glossaryTerms": [],
        "glossaryBindings": [],
        "indexingSettings": {"maxDistinctValuesPerAttribute": 1000},
        "sqlGenerationConfig": {},
    }
    sm_version_mock.get_settings.return_value = sm_version_settings
    sm_version_mock.get_basic_distinct_values_for_model.return_value = {
        "entity1": {"attr1": ["val1", "val2"]}
    }
    sm_version_mock.get_basic_distinct_values_for_attribute.return_value = {
        "values": ["val1", "val2"]
    }
    sm_version_mock.start_update_distinct_values.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    sm_mock.get_version.return_value = sm_version_mock

    new_version_settings = MagicMock()
    new_version_settings.save.return_value = None
    sm_mock.new_version.return_value = new_version_settings

    proj1.get_semantic_model.return_value = sm_mock
    proj1.create_semantic_model.return_value = sm_mock

    # ML task mocks — used by dku ml commands
    mltask_mock = MagicMock()
    mltask_mock.analysis_id = "a1"
    mltask_mock.mltask_id = "t1"
    mltask_mock.get_status.return_value = {
        "guessing": False,
        "training": False,
        "fullModelIds": ["A-PROJ1-a1-t1-s1-pp1-m1"],
    }
    mltask_mock.train.return_value = ["A-PROJ1-a1-t1-s1-pp1-m1"]
    mltask_mock.start_train.return_value = None
    mltask_mock.get_trained_models_ids.return_value = ["A-PROJ1-a1-t1-s1-pp1-m1"]
    mltask_mock.get_trained_model_snippet.return_value = {
        "algorithm": "RandomForest",
        "sessionId": "s1",
        "auc": 0.92,
    }
    ml_details_mock = MagicMock()
    ml_details_mock.get_performance_metrics.return_value = {
        "auc": 0.92,
        "accuracy": 0.88,
    }
    mltask_mock.get_trained_model_details.return_value = ml_details_mock
    mltask_mock.deploy_to_flow.return_value = {
        "savedModelId": "sm1",
        "trainRecipeName": "train_recipe1",
    }
    mltask_mock.redeploy_to_flow.return_value = {"impactsDownstream": False}
    mltask_mock.delete.return_value = None

    # ML task settings mock
    ml_settings_mock = MagicMock()
    ml_settings_mock.get_raw.return_value = {
        "taskType": "PREDICTION",
        "targetVariable": "churn",
    }
    ml_settings_mock.get_all_possible_algorithm_names.return_value = [
        "RandomForest",
        "XGBoost",
        "LogitRegression",
    ]
    ml_settings_mock.get_enabled_algorithm_names.return_value = ["RandomForest"]
    ml_settings_mock.save.return_value = None
    mltask_mock.get_settings.return_value = ml_settings_mock

    # Project-level ML task creation methods
    proj1.create_prediction_ml_task.return_value = mltask_mock
    proj1.create_clustering_ml_task.return_value = mltask_mock
    proj1.create_timeseries_forecasting_ml_task.return_value = mltask_mock
    proj1.create_causal_prediction_ml_task.return_value = mltask_mock
    proj1.list_ml_tasks.return_value = [
        {
            "analysisId": "a1",
            "mlTaskId": "t1",
            "taskType": "PREDICTION",
            "targetVariable": "churn",
        },
    ]
    proj1.get_ml_task.return_value = mltask_mock

    # Analysis mocks
    analysis_mock = MagicMock()
    analysis_mock.analysis_id = "a1"
    analysis_def_mock = MagicMock()
    analysis_def_mock.get_raw.return_value = {
        "analysisId": "a1",
        "inputDataset": "ds1",
    }
    analysis_mock.get_definition.return_value = analysis_def_mock
    analysis_mock.list_ml_tasks.return_value = [
        {"mlTaskId": "t1", "taskType": "PREDICTION"},
    ]
    analysis_mock.delete.return_value = None
    proj1.list_analyses.return_value = [
        {"analysisId": "a1", "inputDataset": "ds1"},
    ]
    proj1.create_analysis.return_value = analysis_mock
    proj1.get_analysis.return_value = analysis_mock

    # Model evaluation stores
    mes_mock = MagicMock()
    mes_mock.id = "mes1"
    mes_mock.evaluation_store_id = "mes1"
    mes_settings_mock = MagicMock()
    mes_settings_mock.get_raw.return_value = {
        "id": "mes1",
        "name": "Churn Eval Store",
        "mesFlavor": "TABULAR",
    }
    mes_mock.get_settings.return_value = mes_settings_mock

    eval_mock = MagicMock()
    eval_mock.evaluation_id = "eval1"
    eval_full_info = MagicMock()
    eval_full_info.get_raw.return_value = {"evaluationId": "eval1", "metrics": {}}
    eval_mock.get_full_info.return_value = eval_full_info

    mes_mock.list_model_evaluations.return_value = [eval_mock]
    mes_mock.get_latest_model_evaluation.return_value = eval_mock
    build_job_mock = MagicMock()
    build_job_mock.id = "job_mes_build"
    mes_mock.build.return_value = build_job_mock
    mes_mock.delete.return_value = None

    proj1.list_model_evaluation_stores.return_value = [mes_mock]
    proj1.create_model_evaluation_store.return_value = mes_mock
    proj1.get_model_evaluation_store.return_value = mes_mock

    # Wiki — DSSWikiArticle has .article_id + .get_data() → DSSWikiArticleData
    wiki_mock = MagicMock()

    class MockArticleData:
        """Mimics DSSWikiArticleData: get_name/get_body/set_name/set_body/save."""

        def __init__(self, name="Home", body="# Welcome"):
            self._name = name
            self._body = body

        def get_name(self):
            return self._name

        def get_body(self):
            return self._body

        def get_metadata(self):
            return {}

        def set_name(self, name):
            self._name = name

        def set_body(self, body):
            self._body = body

        def save(self):
            pass

    article_mock = MagicMock()
    article_mock.article_id = "article1"
    article_mock.get_data.return_value = MockArticleData()
    article_mock.delete.return_value = None

    wiki_mock.list_articles.return_value = [article_mock]
    wiki_mock.get_article.return_value = article_mock
    wiki_mock.create_article.return_value = article_mock
    proj1.get_wiki.return_value = wiki_mock

    # Agent reviews
    review_item = MagicMock()
    review_item.id = "review1"
    review_item.name = "Quality Check"
    review_item.data = {
        "id": "review1",
        "name": "Quality Check",
        "agentSmartId": "agent1",
        "owner": "testuser",
        "helperLLMId": "llm1",
        "traits": [],
    }
    proj1.list_agent_reviews.return_value = [review_item]

    review_mock = MagicMock()
    review_mock.id = "review1"
    review_mock.name = "Quality Check"
    review_mock.agent_id = "agent1"
    review_mock.helper_llm_id = "llm1"
    review_mock.data = {
        "id": "review1",
        "name": "Quality Check",
        "agentSmartId": "agent1",
        "owner": "testuser",
        "helperLLMId": "llm1",
        "traits": [],
    }
    review_mock.get_raw.return_value = review_mock.data
    review_mock.save.return_value = review_mock
    review_mock.delete.return_value = None
    review_mock.add_trait.return_value = None

    # Review tests
    review_test_mock = MagicMock()
    review_test_mock.id = "test1"
    review_test_mock.query = "What is 2+2?"
    review_test_mock.reference_answer = "4"
    review_test_mock.expectations = "Should be numeric"
    review_mock.list_tests.return_value = [review_test_mock]
    review_mock.create_test.return_value = review_test_mock
    review_mock.create_tests_from_dataset.return_value = {
        "createdTestIds": ["t1", "t2", "t3"],
        "error": None,
    }
    review_mock.export_tests_to_dataset.return_value = {
        "exportedTestCount": 3,
        "error": None,
    }

    # Review runs
    review_run_mock = MagicMock()
    review_run_mock.id = "run1"
    review_run_mock.name = "nightly-eval"
    review_run_mock.status = "COMPLETED"
    review_run_mock.agent_id = "agent1"
    review_mock.list_runs.return_value = [review_run_mock]
    review_mock.perform_run.return_value = review_run_mock
    review_mock.get_run.return_value = review_run_mock

    # Review results
    review_result_mock = MagicMock()
    review_result_mock.id = "result1"
    review_result_mock.test_id = "test1"
    review_result_mock.query = "What is 2+2?"
    review_result_mock.status = "PASSED"
    review_run_mock.list_results.return_value = [review_result_mock]

    def _get_agent_review(review_id):
        if review_id == "review1":
            return review_mock
        raise Exception(f"NotFoundException: Agent review {review_id} does not exist")

    proj1.get_agent_review.side_effect = _get_agent_review
    proj1.create_agent_review.return_value = review_mock

    # Code Studios
    cs_list_item = MagicMock()
    cs_list_item.id = "cs1"
    cs_list_item.name = "My Studio"
    cs_list_item.owner = "testuser"
    cs_list_item.template_id = "tpl1"
    cs_list_item.template_label = "Python Notebook"
    proj1.list_code_studios.return_value = [cs_list_item]

    cs_mock = MagicMock()
    cs_settings = MagicMock()
    cs_settings.get_raw.return_value = {
        "id": "cs1",
        "name": "My Studio",
        "templateId": "tpl1",
        "owner": "testuser",
    }
    cs_settings.id = "cs1"
    cs_settings.name = "My Studio"
    cs_settings.template_id = "tpl1"
    cs_settings.owner = "testuser"
    cs_mock.get_settings.return_value = cs_settings
    cs_status = MagicMock()
    cs_status.state = "STOPPED"
    cs_status.last_state_change = None
    cs_status.get_raw.return_value = {"state": "STOPPED"}
    cs_mock.get_status.return_value = cs_status
    cs_mock.restart.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    cs_mock.stop.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    cs_mock.delete.return_value = None
    cs_mock.change_owner.return_value = {"id": "cs1", "owner": "newuser"}
    cs_mock.id = "cs1"
    proj1.get_code_studio.return_value = cs_mock
    proj1.create_code_studio.return_value = cs_mock

    # Code Studio templates (client-level)
    cs_tpl = MagicMock()
    cs_tpl.id = "tpl1"
    cs_tpl.label = "Python Notebook"
    client.list_code_studio_templates.return_value = [cs_tpl]

    # API Deployer
    api_deployer_mock = MagicMock()
    api_deployer_mock.list_infras.return_value = [
        {"infraBasicInfo": {"id": "infra1", "type": "STATIC"}},
    ]
    api_deployer_mock.list_services.return_value = [
        {"serviceBasicInfo": {"id": "svc1"}},
    ]

    api_svc_handle = MagicMock()
    api_svc_settings = MagicMock()
    api_svc_settings.get_raw.return_value = {"id": "svc1"}
    api_svc_handle.get_settings.return_value = api_svc_settings
    api_deployer_mock.get_service.return_value = api_svc_handle

    api_deployer_mock.list_deployments.return_value = [
        {
            "deploymentBasicInfo": {
                "id": "dep1",
                "serviceId": "svc1",
                "infraId": "infra1",
            }
        },
    ]

    api_dep_handle = MagicMock()
    api_dep_settings = MagicMock()
    api_dep_settings.get_raw.return_value = {
        "id": "dep1",
        "serviceId": "svc1",
        "infraId": "infra1",
    }
    api_dep_handle.get_settings.return_value = api_dep_settings
    api_dep_handle.get_light_status.return_value = {"health": "HEALTHY"}
    api_dep_handle.start_update.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    api_dep_handle.delete.return_value = None
    api_deployer_mock.get_deployment.return_value = api_dep_handle
    api_deployer_mock.create_deployment.return_value = api_dep_handle

    client.get_apideployer.return_value = api_deployer_mock

    # Project Deployer
    proj_deployer_mock = MagicMock()
    proj_deployer_mock.list_infras.return_value = [
        {"infraBasicInfo": {"id": "auto_infra1", "type": "STATIC"}},
    ]
    proj_deployer_mock.list_projects.return_value = [
        {"projectBasicInfo": {"id": "dp1"}},
    ]
    proj_deployer_mock.list_deployments.return_value = [
        {
            "deploymentBasicInfo": {
                "id": "pdep1",
                "projectKey": "dp1",
                "infraId": "auto_infra1",
            }
        },
    ]

    proj_dep_handle = MagicMock()
    proj_dep_settings = MagicMock()
    proj_dep_settings.get_raw.return_value = {
        "id": "pdep1",
        "projectId": "dp1",
        "infraId": "auto_infra1",
    }
    proj_dep_handle.get_settings.return_value = proj_dep_settings
    proj_dep_handle.get_light_status.return_value = {"health": "HEALTHY"}
    proj_dep_handle.start_update.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    proj_dep_handle.delete.return_value = None
    proj_deployer_mock.get_deployment.return_value = proj_dep_handle
    proj_deployer_mock.create_deployment.return_value = proj_dep_handle

    client.get_projectdeployer.return_value = proj_deployer_mock

    # Notebooks
    jupyter_nb = MagicMock()
    jupyter_nb.name = "my_notebook"
    proj1.list_jupyter_notebooks.return_value = [jupyter_nb]

    sql_nb = MagicMock()
    sql_nb.name = "my_sql_notebook"
    sql_nb._data = {
        "id": "sql_nb1",
        "name": "my_sql_notebook",
        "connection": "postgres",
    }
    proj1.list_sql_notebooks.return_value = [sql_nb]

    nb_mock = MagicMock()
    nb_content = MagicMock()
    nb_content.get_raw.return_value = {"cells": [], "metadata": {}}
    nb_content.save.return_value = None
    nb_mock.get_content.return_value = nb_content
    nb_mock.get_sessions.return_value = []
    nb_mock.unload.return_value = {}
    nb_mock.delete.return_value = None
    nb_mock.clear_outputs.return_value = None
    nb_mock.name = "my_notebook"
    proj1.get_jupyter_notebook.return_value = nb_mock
    proj1.create_jupyter_notebook.return_value = nb_mock

    sql_nb_mock = MagicMock()
    sql_nb_content = MagicMock()
    sql_nb_content.get_raw.return_value = {"connection": "postgres", "cells": []}
    sql_nb_mock.get_content.return_value = sql_nb_content
    sql_history = MagicMock()
    sql_history.get_raw = MagicMock(return_value={"queries": []})
    sql_nb_mock.get_history.return_value = sql_history
    sql_nb_mock.delete.return_value = None
    proj1.get_sql_notebook.return_value = sql_nb_mock

    proj1.list_running_notebooks.return_value = [
        {
            "projectKey": "PROJ1",
            "name": "my_notebook",
            "kernelId": "k1",
            "sessionId": "s1",
        }
    ]

    # Discussions (on dataset_mock since it's most common)
    disc_mock = MagicMock()
    disc_metadata = {"id": "disc1", "topic": "Data quality issue"}
    disc_mock.get_metadata.return_value = disc_metadata
    disc_reply = MagicMock()
    disc_reply.get_text.return_value = "Fixed in v2"
    disc_reply.get_author.return_value = "admin"
    disc_mock.get_replies.return_value = [disc_reply]
    disc_mock.add_reply.return_value = None

    discussions_mock = MagicMock()
    discussions_mock.list_discussions.return_value = [disc_mock]
    discussions_mock.get_discussion.return_value = disc_mock
    discussions_mock.create_discussion.return_value = disc_mock

    dataset_mock.get_object_discussions.return_value = discussions_mock
    recipe_mock.get_object_discussions.return_value = discussions_mock

    client.get_project.return_value = proj1

    # SQL — mock DSSSQLQuery object (has get_schema + iter_rows, not dict)
    sql_result_mock = MagicMock()
    sql_result_mock.get_schema.return_value = [
        {"name": "col1", "type": "string"},
        {"name": "col2", "type": "string"},
    ]
    sql_result_mock.iter_rows.return_value = iter([["val1", "val2"], ["val3", "val4"]])
    client.sql_query.return_value = sql_result_mock

    # User create
    client.create_user.return_value = {"login": "newuser", "displayName": "New User"}

    # Connection create
    client.create_connection.return_value = MagicMock()

    # Instance variables
    client.get_variables.return_value = {
        "standard": {"instance_var": "ival"},
        "local": {},
    }
    client.set_variables.return_value = None

    # Plugins — dataikuapi quirk: returns dicts
    client.list_plugins.return_value = [
        {"id": "my-plugin", "version": "1.0.0", "isDev": True},
        {"id": "other-plugin", "version": "2.1.0", "isDev": False},
    ]

    # Code environments — dataikuapi quirk: returns dicts
    client.list_code_envs.return_value = [
        {
            "envName": "py39",
            "envLang": "PYTHON",
            "deploymentMode": "DESIGN_MANAGED",
            "owner": "admin",
        },
    ]

    # Code env mock — real API uses pythonInterpreter not pythonVersion
    codeenv_mock = MagicMock()
    codeenv_mock.get_definition.return_value = {
        "envName": "py39",
        "envLang": "PYTHON",
        "deploymentMode": "DESIGN_MANAGED",
        "owner": "admin",
        "specPackageList": "pandas\nnumpy\n",
        "desc": {"pythonInterpreter": "PYTHON39", "corePackagesSet": "PANDAS13"},
    }
    codeenv_mock.delete.return_value = None
    codeenv_mock.update_packages.return_value = None
    client.get_code_env.return_value = codeenv_mock

    # Connections — admin endpoint, returns dict of dicts
    client.list_connections.return_value = {
        "filesystem_managed": {
            "type": "Filesystem",
            "allowWrite": True,
            "allowManagedDatasets": True,
        },
    }
    conn_mock = MagicMock()
    conn_mock.test.return_value = {"ok": True}
    conn_settings_mock = MagicMock()
    conn_settings_mock.get_raw.return_value = {
        "name": "filesystem_managed",
        "type": "Filesystem",
    }
    conn_mock.get_settings.return_value = conn_settings_mock
    conn_mock.delete.return_value = None
    client.get_connection.return_value = conn_mock

    # Users
    client.list_users.return_value = [
        {
            "login": "admin",
            "displayName": "Admin User",
            "email": "admin@test.com",
            "groups": ["admin"],
        },
        {
            "login": "testuser",
            "displayName": "Test User",
            "email": "test@test.com",
            "groups": ["data_team"],
        },
    ]

    # User get/delete mocks
    user_mock = MagicMock()
    user_settings_mock = MagicMock()
    user_settings_mock.get_raw.return_value = {
        "login": "testuser",
        "displayName": "Test User",
        "email": "test@test.com",
    }
    user_mock.get_settings.return_value = user_settings_mock
    user_mock.delete.return_value = None
    client.get_user.return_value = user_mock

    # Saved model delete/usages (proj1's model_mock already exists above)
    model_mock.delete.return_value = None
    model_mock.get_usages.return_value = {"usedIn": []}

    # Plugin file operations — list_files returns tree, get_file returns context manager
    import io

    plugin_tree = [
        {
            "name": "python-lib",
            "path": "python-lib",
            "children": [
                {"name": "mylib.py", "path": "python-lib/mylib.py"},
            ],
        },
        {"name": "plugin.json", "path": "plugin.json"},
    ]

    plugin_file_cm = MagicMock()
    plugin_file_cm.__enter__ = MagicMock(
        return_value=io.BytesIO(b"# plugin file content")
    )
    plugin_file_cm.__exit__ = MagicMock(return_value=False)

    plugin_file_mock = client.get_plugin.return_value
    plugin_file_mock.list_files.return_value = plugin_tree
    plugin_file_mock.get_file.return_value = plugin_file_cm
    plugin_file_mock.put_file.return_value = None

    return client


@pytest.fixture
def patch_client(mock_client):
    """Patch get_client everywhere it's imported."""
    with (
        patch("dku_cli.client.get_client", return_value=mock_client),
        patch("dku_cli.helpers.get_client", return_value=mock_client),
    ):
        yield mock_client
