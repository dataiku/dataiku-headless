"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_quiet():
    """Reset quiet mode between tests so --quiet in one test doesn't leak."""
    from dku_cli.output import set_quiet

    set_quiet(False)
    yield
    set_quiet(False)


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

    # Library mock
    library_mock = MagicMock()
    library_mock.list_contents.return_value = [
        {"path": "python/mylib/__init__.py", "size": 0},
        {"path": "python/mylib/utils.py", "size": 256},
    ]
    library_mock.get_file.return_value = b"# utils.py\ndef transform(df):\n    return df"
    library_mock.put_file.return_value = None
    library_mock.delete_file.return_value = None
    library_mock.add_folder.return_value = None
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

    # Flow schema propagation
    propagation_mock = MagicMock()
    propagation_mock.start.return_value = MagicMock(
        wait_for_result=MagicMock(return_value={"success": True})
    )
    flow_mock.start_schema_propagation.return_value = propagation_mock

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
    proj1.get_recipe.return_value = recipe_mock

    # Recipe builder mock for new_recipe()
    recipe_builder = MagicMock()
    recipe_builder.with_input.return_value = recipe_builder
    recipe_builder.with_existing_output.return_value = recipe_builder
    recipe_builder.build.return_value = recipe_mock
    proj1.new_recipe.return_value = recipe_builder

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

    # Webapp mock — get_state returns object with .running property
    webapp_mock = MagicMock()
    webapp_state = MagicMock()
    webapp_state.running = True
    webapp_mock.get_state.return_value = webapp_state
    webapp_mock.start_or_restart_backend.return_value = None
    webapp_mock.stop_backend.return_value = None
    proj1.get_webapp.return_value = webapp_mock

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
    embeddings_mock.with_text.return_value = embeddings_mock
    embeddings_response = MagicMock()
    embeddings_response.vectors = [[0.1, 0.2, 0.3]]
    embeddings_mock.execute.return_value = embeddings_response
    llm_mock.new_embeddings.return_value = embeddings_mock

    proj1.get_llm.return_value = llm_mock

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
    proj1.get_agent.return_value = agent_mock

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

    # Wiki
    wiki_mock = MagicMock()
    wiki_mock.list_articles.return_value = [
        {"id": "article1", "article": {"name": "Home", "id": "article1"}},
    ]
    article_mock = MagicMock()
    article_mock.get_data.return_value = {
        "article": {"name": "Home", "id": "article1"},
        "body": "# Welcome",
    }
    wiki_mock.get_article.return_value = article_mock
    wiki_mock.create_article.return_value = article_mock
    proj1.get_wiki.return_value = wiki_mock

    client.get_project.return_value = proj1

    # SQL
    client.sql_query.return_value = {
        "columns": ["col1", "col2"],
        "rows": [["val1", "val2"], ["val3", "val4"]],
    }

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
