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
        {"name": "ds1", "type": "UploadedFiles", "schema": {"columns": [{"name": "col1", "type": "string"}]}},
    ]
    proj1.list_recipes.return_value = [
        {"name": "recipe1", "type": "python", "tags": ["etl"]},
    ]

    # Scenarios — list_scenarios returns dict-like items (DSSScenarioListItem)
    scen_item = MagicMock()
    scen_item.get.side_effect = lambda k, d="": {
        "id": "scen1", "name": "Build All", "active": True, "type": "step_based",
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

    # add_file() returns DSSLibraryFile
    library_mock.add_file.return_value = lib_file_mock

    # get_folder()/add_folder() return DSSLibraryFolder
    lib_folder_mock = MagicMock()
    lib_folder_mock.list.return_value = [lib_item1, lib_item2]
    lib_folder_mock.add_file.return_value = lib_file_mock
    lib_folder_mock.add_folder.return_value = lib_folder_mock
    lib_folder_mock.get_folder.return_value = lib_folder_mock
    library_mock.get_folder.return_value = lib_folder_mock
    library_mock.add_folder.return_value = lib_folder_mock

    proj1.get_library.return_value = library_mock

    # Flow — real API returns DSSProjectFlowGraph with .nodes and .data attrs
    flow_mock = MagicMock()
    graph_mock = MagicMock()
    graph_mock.nodes = {
        "ds1": {"type": "COMPUTABLE_DATASET", "subType": "", "ref": "ds1", "successors": ["recipe1"]},
        "recipe1": {"type": "RUNNABLE_RECIPE", "subType": "python", "ref": "recipe1", "successors": []},
    }
    graph_mock.data = {"nodes": graph_mock.nodes}
    graph_mock.get_successors.side_effect = AttributeError("not implemented")
    flow_mock.get_graph.return_value = graph_mock

    # Flow zones
    zone_mock = MagicMock()
    zone_mock.id = "zone1"
    zone_mock.name = "Default"
    flow_mock.list_zones.return_value = [zone_mock]
    flow_mock.create_zone.return_value = zone_mock

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

    # Dataset mocks — iter_rows returns lists (not dicts)
    dataset_mock = MagicMock()
    dataset_mock.get_definition.return_value = {
        "schema": {"columns": [{"name": "col1", "type": "string"}, {"name": "col2", "type": "int"}]},
    }
    dataset_mock.iter_rows.return_value = iter([
        ["a", "1"],
        ["b", "2"],
    ])
    build_job = MagicMock()
    build_job.id = "job_build_1"
    build_job.get_status.return_value = {"baseStatus": {"state": "DONE"}}
    dataset_mock.build.return_value = build_job
    dataset_mock.delete.return_value = None
    dataset_mock.clear.return_value = None
    dataset_mock.set_definition.return_value = None
    dataset_mock.uploaded_add_file.return_value = None

    # autodetect_settings returns a DSSDatasetSettings-like object
    autodetect_result = MagicMock()
    autodetect_result.get_raw.return_value = {
        "formatType": "csv",
        "formatParams": {"style": "excel", "separator": ","},
        "schema": {"columns": [{"name": "col1", "type": "string"}, {"name": "col2", "type": "int"}]},
    }
    autodetect_result.save.return_value = None
    dataset_mock.autodetect_settings.return_value = autodetect_result

    proj1.get_dataset.return_value = dataset_mock

    # create_dataset returns a dataset mock
    proj1.create_dataset.return_value = dataset_mock

    managed_dataset_builder = MagicMock()
    managed_dataset_builder.with_store_into.return_value = managed_dataset_builder
    managed_dataset_builder.create.return_value = dataset_mock
    proj1.new_managed_dataset.return_value = managed_dataset_builder

    # Scenario create mock
    new_scenario_mock = MagicMock()
    new_scenario_mock.id = "new_scen"
    proj1.create_scenario.return_value = new_scenario_mock

    # Scenario run/abort/status/delete/definition mocks
    scenario_mock = MagicMock()
    scenario_mock.run.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={
            "scenarioRun": {"result": {"outcome": "SUCCESS"}}
        })
    )
    scenario_mock.abort.return_value = None
    scenario_mock.delete.return_value = None

    # get_definition returns a settings object with .get_raw()
    scenario_def_mock = MagicMock()
    scenario_def_mock.get_raw.return_value = {
        "type": "step_based",
        "name": "Build All",
        "params": {},
    }
    scenario_mock.get_definition.return_value = scenario_def_mock
    scenario_mock.set_definition.return_value = None

    # get_last_runs returns DSSScenarioRun objects with properties
    run_mock = MagicMock()
    run_mock.id = "run1"
    run_mock.start_time = "2025-01-01T00:00:00"
    run_mock.outcome = "SUCCESS"
    run_mock.trigger = {"type": "manual"}
    scenario_mock.get_last_runs.return_value = [run_mock]
    proj1.get_scenario.return_value = scenario_mock

    # Job mocks
    proj1.list_jobs.return_value = [
        {
            "baseStatus": {
                "def": {"id": "job1", "initiator": "testuser"},
                "state": "DONE",
                "timing": {"startTime": "2025-01-01T00:00:00", "endTime": "2025-01-01T00:01:00"},
            }
        },
    ]
    job_mock = MagicMock()
    job_mock.get_status.return_value = {
        "baseStatus": {
            "def": {"id": "job1", "initiator": "testuser"},
            "state": "DONE",
            "timing": {"startTime": "2025-01-01T00:00:00", "endTime": "2025-01-01T00:01:00"},
        }
    }
    job_mock.get_log.return_value = "Log line 1\nLog line 2"
    job_mock.abort.return_value = None
    proj1.get_job.return_value = job_mock

    # Job builder mock for new_job() — used by dku job run, dataset build --type, recipe run --type
    job_builder_mock = MagicMock()
    job_builder_mock.with_output.return_value = job_builder_mock
    job_builder_mock.with_auto_update_schema_before_each_recipe_run.return_value = job_builder_mock
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
    proj1.get_webapp.return_value = webapp_mock

    # Dashboards
    proj1.list_dashboards.return_value = [
        {"id": "dashboard1", "name": "Sales Dashboard", "pages": [], "tags": []},
    ]
    dashboard_mock = MagicMock()
    dashboard_settings = MagicMock()
    dashboard_settings.get_raw.return_value = {
        "id": "dashboard1",
        "name": "Sales Dashboard",
        "pages": [{"id": "page1", "title": "Overview", "tiles": []}],
    }
    dashboard_settings.save.return_value = None
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
    insight_settings.get_raw.return_value = {
        "id": "insight1",
        "name": "Sales Chart",
        "type": "chart",
        "params": {},
    }
    insight_settings.save.return_value = None
    insight_mock.get_settings.return_value = insight_settings
    insight_mock.delete.return_value = None
    proj1.get_insight.return_value = insight_mock
    new_insight_mock = MagicMock()
    new_insight_mock.insight_id = "new_insight_1"
    proj1.create_insight.return_value = new_insight_mock

    # Managed folder mock
    folder_mock = MagicMock()
    folder_mock.list_contents.return_value = {
        "items": [
            {"path": "/data.csv", "size": 1024, "lastModified": 1700000000000},
        ]
    }
    folder_mock.put_file.return_value = None
    proj1.get_managed_folder.return_value = folder_mock

    # Saved model mock — uses get_settings().get_raw() and get_active_version()
    model_mock = MagicMock()
    model_settings = MagicMock()
    model_settings.get_raw.return_value = {"name": "My Model", "type": "PREDICTION"}
    model_mock.get_settings.return_value = model_settings
    model_mock.get_active_version.return_value = {"id": "v1"}
    model_mock.list_versions.return_value = [
        {"id": "v1", "active": True, "snippet": {"algorithm": "RandomForest"}},
    ]
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
                {"id": "azureopenai:Azure_AI_Connection:4o", "type": "CHAT", "description": "Azure OpenAI 4o"},
            ],
            "TEXT_EMBEDDING_EXTRACTION": [
                {"id": "embedding1", "type": "EMBEDDINGS", "description": "Embedding model"},
            ],
        }
        return by_purpose.get(purpose, [])

    def _get_llm(llm_id):
        llms = {
            "llm1": llm_mock,
            "embedding1": embedding_llm_mock,
            "azureopenai:Azure_AI_Connection:4o": llm_mock,
        }
        return llms[llm_id]

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
    api_service_mock.list_packages.return_value = [{"id": "pkg1", "createdOn": "2025-01-01"}]
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
    agent_mock.get_status.return_value = {"state": "RUNNING"}
    agent_mock.delete.return_value = None
    agent_mock.wake_up.return_value = None
    agent_mock.shutdown.return_value = None
    agent_mock.id = "agent1"

    # Agent with BLOCKS_GRAPH mode (for agent-block commands)
    agent_blocks_mock = MagicMock()
    agent_blocks_version_data = {
        "versionId": "v1",
        "toolsUsingAgentSettings": {
            "mode": "BLOCKS_GRAPH",
            "startingBlockId": "init_state",
            "blocks": [
                {
                    "type": "SET_STATE_ENTRIES", "id": "init_state",
                    "entriesToSet": [{"secret": False, "key": "status", "value": "started"}],
                    "nextBlock": "classify",
                },
                {
                    "type": "LLM_REQUEST", "id": "classify", "llmId": "llm1",
                    "outputMode": "SAVE_TO_STATE", "outputStateKey": "intent",
                    "nextBlock": "emit_result",
                },
                {
                    "type": "EMIT_OUTPUT", "id": "emit_result",
                    "templateType": "CEL_EXPANSION", "template": "Done",
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
    agent_blocks_mock.get_status.return_value = {"state": "RUNNING"}
    agent_blocks_mock.delete.return_value = None
    agent_blocks_mock.id = "agent_blocks"

    # Route get_agent by agent_id
    def _get_agent(agent_id):
        if agent_id == "agent1":
            return agent_mock
        if agent_id == "agent_blocks":
            return agent_blocks_mock
        raise Exception(f"NotFoundException: Agent {agent_id} does not exist")
    proj1.get_agent.side_effect = _get_agent

    # create_agent returns agent with .id
    new_agent_mock = MagicMock()
    new_agent_mock.id = "new_agent_1"
    proj1.create_agent.return_value = new_agent_mock

    # Agent tools
    proj1.list_agent_tools.return_value = [{"id": "tool1", "name": "My Tool", "type": "python"}]
    tool_mock = MagicMock()
    tool_settings = MagicMock()
    tool_settings.get_raw.return_value = {"id": "tool1", "name": "My Tool"}
    tool_mock.get_settings.return_value = tool_settings
    tool_mock.run.return_value = {"result": "success", "output": "done"}
    tool_mock.delete.return_value = None
    proj1.get_agent_tool.return_value = tool_mock

    # Knowledge banks
    proj1.list_knowledge_banks.return_value = [{"id": "kb1", "name": "My KB"}]
    kb_mock = MagicMock()
    kb_settings = MagicMock()
    kb_settings.get_raw.return_value = {"id": "kb1", "name": "My KB"}
    kb_mock.get_settings.return_value = kb_settings
    kb_mock.build.return_value = MagicMock(wait_for_result=MagicMock(return_value={"success": True}))
    kb_mock.search.return_value = [{"content": "result1", "score": 0.95}]
    kb_mock.delete.return_value = None
    proj1.get_knowledge_bank.return_value = kb_mock
    proj1.create_knowledge_bank.return_value = kb_mock

    # NOTE: Eval store + comparison fixtures removed — add back when those command groups land.

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
        {"envName": "py39", "envLang": "PYTHON", "deploymentMode": "DESIGN_MANAGED", "owner": "admin"},
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
    client.get_connection.return_value = conn_mock

    # Users
    client.list_users.return_value = [
        {"login": "admin", "displayName": "Admin User", "email": "admin@test.com", "groups": ["admin"]},
        {"login": "testuser", "displayName": "Test User", "email": "test@test.com", "groups": ["data_team"]},
    ]

    return client


@pytest.fixture
def patch_client(mock_client):
    """Patch get_client everywhere it's imported."""
    with patch("dku_cli.client.get_client", return_value=mock_client), \
         patch("dku_cli.helpers.get_client", return_value=mock_client):
        yield mock_client
