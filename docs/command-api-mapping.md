# Command → dataikuapi Mapping

Every `dku` CLI command maps to one or more `dataikuapi` calls. This table is the authoritative reference for which Python API calls each command wraps.

| CLI Command | dataikuapi Call |
|---|---|
| `dku project list` | `client.list_project_keys()` + `get_project().get_metadata()` |
| `dku project get KEY` | `get_project(KEY).get_metadata()` + `.get_status()` |
| `dku project export KEY` | `get_project(KEY).export_to_file()` |
| `dku project create KEY` | `client.create_project(key, name, owner, description)` |
| `dku project delete KEY` | `get_project(KEY).delete()` |
| `dku project duplicate KEY` | `get_project(KEY).duplicate(target_project_key, target_project_name)` |
| `dku project variables` | `get_project(KEY).get_variables()` |
| `dku project set-variables` | `get_project(KEY).set_variables(obj)` |
| `dku project permissions` | `get_project(KEY).get_permissions()` |
| `dku project set-permissions` | `get_project(KEY).set_permissions(perms)` |
| `dku project tags` | `get_project(KEY).get_metadata()` → `.tags` |
| `dku dataset list` | `project.list_datasets()` |
| `dku dataset schema NAME` | `get_dataset(NAME).get_definition()` |
| `dku dataset head NAME` | `get_dataset(NAME).iter_rows()` |
| `dku dataset build NAME` | `get_dataset(NAME).build()` |
| `dku dataset create NAME` | `project.create_dataset(name, type, params)` |
| `dku dataset upload NAME FILE` | `get_dataset(NAME).uploaded_add_file(fp, filename)` |
| `dku dataset delete NAME` | `get_dataset(NAME).delete()` |
| `dku dataset clear NAME` | `get_dataset(NAME).clear()` |
| `dku dataset get-definition` | `get_dataset(NAME).get_definition()` |
| `dku dataset set-definition` | `get_dataset(NAME).set_definition(def)` |
| `dku dataset set-schema` | `get_dataset(NAME).get_definition()` → update schema → `set_definition()` |
| `dku recipe list` | `project.list_recipes()` |
| `dku recipe get NAME` | `get_recipe(NAME).get_settings().get_recipe_raw_definition()` |
| `dku recipe run NAME` | `get_recipe(NAME).run()` |
| `dku recipe create NAME` | `project.new_recipe(type, name).with_input().with_existing_output().build()` |
| `dku recipe delete NAME` | `get_recipe(NAME).delete()` |
| `dku recipe set-code NAME` | `get_recipe(NAME).get_settings().set_payload(code)` → `.save()` |
| `dku recipe get-code NAME` | `get_recipe(NAME).get_settings().get_payload()` |
| `dku recipe set-definition` | `get_recipe(NAME).get_settings().get_recipe_raw_definition().update()` → `.save()` |
| `dku recipe add-input NAME` | `get_recipe(NAME).get_settings().add_input(role, ref)` → `.save()` |
| `dku recipe add-output NAME` | `get_recipe(NAME).get_settings().add_output(role, ref)` → `.save()` |
| `dku recipe check-schema NAME` | `get_recipe(NAME).compute_schema_updates()` |
| `dku recipe apply-schema NAME` | `get_recipe(NAME).compute_schema_updates().apply()` |
| `dku recipe create-embed NAME` | `project.new_recipe("nlp_llm_rag_embedding", NAME)` → `.with_input()` → `.with_output_knowledge_bank()` → `.build()` |
| `dku recipe create-embed-docs NAME` | `project.new_recipe("embed_documents", NAME)` → `.with_input()` → `.with_vlm()` → `.with_output_knowledge_bank()` → `.build()` |
| `dku recipe create-extract NAME` | `project.new_recipe("extract_content", NAME)` → `.with_input()` → `.with_vlm()` → `.with_existing_output()` → `.build()` |
| `dku recipe create-llm-eval NAME` | `project.new_recipe("nlp_llm_evaluation", NAME)` → `.with_input()` → `.with_output()` → `.with_output_metrics()` → `.with_output_evaluation_store()` → `.build()` + `settings.obj_payload` config |
| `dku recipe create-agent-eval NAME` | `project.new_recipe("nlp_agent_evaluation", NAME)` → `.with_input()` → `.with_output()` → `.with_output_metrics()` → `.with_output_evaluation_store()` → `.build()` + `settings.obj_payload` config |
| `dku scenario list` | `project.list_scenarios()` |
| `dku scenario run ID` | `get_scenario(ID).run()` |
| `dku scenario abort ID` | `get_scenario(ID).abort()` |
| `dku scenario status ID` | `get_scenario(ID).get_last_runs()` |
| `dku scenario create NAME` | `project.create_scenario(name, type, definition)` |
| `dku scenario delete ID` | `get_scenario(ID).delete()` |
| `dku scenario get-definition` | `get_scenario(ID).get_definition().get_raw()` |
| `dku scenario set-definition` | `get_scenario(ID).set_definition(def)` |
| `dku job list` | `project.list_jobs()` |
| `dku job run --target NAME` | `project.new_job(type).with_output(name).with_auto_update_schema_before_each_recipe_run(bool).start()` |
| `dku job status ID` | `get_job(ID).get_status()` |
| `dku job log ID` | `get_job(ID).get_log()` |
| `dku job abort ID` | `get_job(ID).abort()` |
| `dku job wait ID` | `get_job(ID).get_status()` (poll loop) |
| `dku plugin list` | `client.list_plugins()` |
| `dku plugin push ZIP` | `plugin.update_from_zip()` or `install_plugin_from_archive()` |
| `dku plugin settings ID` | `plugin.get_settings().get_raw()` |
| `dku code-env list` | `client.list_code_envs()` |
| `dku code-env get NAME` | `client.get_code_env(lang, name).get_definition()` |
| `dku code-env create NAME` | `client.create_code_env()` |
| `dku code-env delete NAME` | `get_code_env().delete()` |
| `dku code-env update NAME` | `get_code_env().update_packages()` |
| `dku connection list` | `client.list_connections()` |
| `dku connection create NAME` | `client.create_connection(name, type, params)` |
| `dku connection test NAME` | `get_connection(NAME).test()` |
| `dku model list` | `project.list_saved_models()` |
| `dku model get ID` | `get_saved_model(ID).get_status()` |
| `dku model versions ID` | `get_saved_model(ID).list_versions()` |
| `dku folder list` | `project.list_managed_folders()` |
| `dku folder ls ID` | `get_managed_folder(ID).list_contents()` |
| `dku folder upload ID FILE` | `get_managed_folder(ID).put_file()` |
| `dku folder download ID PATH` | `get_managed_folder(ID).get_file()` |
| `dku llm list` | `project.list_llms()` |
| `dku llm completion ID MSG` | `get_llm(ID).new_completion().with_message().execute()` |
| `dku llm embeddings ID` | `get_llm(ID).new_embeddings().with_text().execute()` |
| `dku webapp list` | `project.list_webapps()` |
| `dku webapp start ID` | `get_webapp(ID).start_or_restart_backend()` |
| `dku webapp stop ID` | `get_webapp(ID).stop_backend()` |
| `dku webapp status ID` | `get_webapp(ID).get_state()` |
| `dku macro list` | `project.list_macros()` |
| `dku macro run ID` | `get_macro(ID).run()` |
| `dku user list` | `client.list_users()` |
| `dku user create LOGIN` | `client.create_user(login, password, display_name, email, groups)` |
| `dku flow graph` | `get_flow().get_graph()` |
| `dku flow zones` | `get_flow().list_zones()` |
| `dku flow create-zone NAME` | `get_flow().create_zone(name)` |
| `dku flow propagate DATASET` | `get_flow().new_schema_propagation(dataset).start().wait_for_result()` |
| `dku flow check` | `get_flow().start_tool("CHECK_CONSISTENCY")` |
| `dku flow sources` | `get_flow().get_graph()` → find nodes with no upstream |
| `dku flow successors NODE` | `get_flow().get_graph().get_successors(node)` |
| `dku library list` | `get_project().get_library().list_contents(path)` |
| `dku library read PATH` | `get_project().get_library().get_file(path)` |
| `dku library write PATH` | `get_project().get_library().put_file(path, data)` |
| `dku library delete PATH` | `get_project().get_library().delete_file(path)` |
| `dku library mkdir PATH` | `get_project().get_library().add_folder(path)` |
| `dku agent list` | `project.list_agents()` |
| `dku agent create NAME` | `project.create_agent(name)` |
| `dku agent get ID` | `get_agent(ID).get_settings().get_raw()` |
| `dku agent delete ID` | `get_agent(ID).delete()` |
| `dku agent wake-up ID` | `get_agent(ID).wake_up()` |
| `dku agent shutdown ID` | `get_agent(ID).shutdown()` |
| `dku agent status ID` | `get_agent(ID).get_status()` |
| `dku agent add-tool ID` | `get_agent(ID).get_settings()` → modify tools → `.save()` |
| `dku agent set-llm ID` | `get_agent(ID).get_settings()` → set llmId → `.save()` |
| `dku agent-tool list` | `project.list_agent_tools()` |
| `dku agent-tool get ID` | `get_agent_tool(ID).get_settings().get_raw()` |
| `dku agent-tool run ID` | `get_agent_tool(ID).run(input)` |
| `dku agent-tool delete ID` | `get_agent_tool(ID).delete()` |
| `dku knowledge list` | `project.list_knowledge_banks()` |
| `dku knowledge create NAME` | `project.create_knowledge_bank(name)` |
| `dku knowledge get ID` | `get_knowledge_bank(ID).get_settings().get_raw()` |
| `dku knowledge build ID` | `get_knowledge_bank(ID).build()` |
| `dku knowledge search ID` | `get_knowledge_bank(ID).search(query, max_documents)` |
| `dku knowledge delete ID` | `get_knowledge_bank(ID).delete()` |
| `dku bundle list` | `project.list_exported_bundles()` |
| `dku bundle export ID` | `project.export_bundle(id)` |
| `dku bundle download ID` | `project.download_exported_bundle_archive_to_file(id, path)` |
| `dku bundle import PATH` | `project.import_bundle_from_archive(f)` |
| `dku bundle activate ID` | `project.preload_bundle(id)` + `project.activate_bundle(id)` |
| `dku api-service list` | `project.list_api_services()` |
| `dku api-service create ID` | `project.create_api_service(id)` |
| `dku api-service get ID` | `get_api_service(ID).get_settings().get_raw()` |
| `dku api-service create-package` | `get_api_service(ID).create_package()` |
| `dku api-service list-packages` | `get_api_service(ID).list_packages()` |
| `dku wiki list` | `get_wiki().list_articles()` |
| `dku wiki create TITLE` | `get_wiki().create_article(title, body)` |
| `dku wiki get ID` | `get_wiki().get_article(id).get_data()` |
| `dku sql query SQL` | `client.sql_query(query, connection)` |
| `dku config set/get` | local config file |
| `dku config variables` | `client.get_variables()` |
| `dku config set-variables` | `client.set_variables(vars)` |
| `dku whoami` | `client.get_auth_info()` |
