# dku CLI — Command Reference

All 139 commands across 25 groups.

---

### `dku project`

```bash
dku project list                              # List all projects
dku project get MYPROJECT                     # Project details
dku project create MYPROJECT --name "Name"    # Create project
dku project delete MYPROJECT --confirm        # Delete (irreversible)
dku project duplicate PROJ --target-key NEW --target-name "New"
dku project export MYPROJECT -d ./exports     # Export as ZIP
dku project variables -P MYPROJECT            # Show variables
dku project set-variables -P MYPROJECT --set env=production
dku project permissions -P MYPROJECT          # Show permissions
dku project set-permissions -P MYPROJECT --definition @perms.json
dku project tags -P MYPROJECT                 # Show tags
```

### `dku dataset`

```bash
dku dataset list -P MYPROJECT                 # List datasets
dku dataset create raw_data --type UploadedFiles -P MYPROJECT
dku dataset upload raw_data ./data.csv -P MYPROJECT  # Upload + auto-detect format/schema
dku dataset schema my_dataset -P MYPROJECT    # Show schema
dku dataset set-schema my_dataset -P MYPROJECT --definition '{"columns":[...]}'
dku dataset head my_dataset -P MYPROJECT -n 5 # Preview rows
dku dataset build my_dataset --wait           # Build and wait
dku dataset get-definition my_dataset -P MYPROJECT  # Full JSON
dku dataset get-definition my_dataset -P MYPROJECT -o json
dku dataset set-definition my_dataset -P MYPROJECT --definition @def.json
dku dataset clear my_dataset -P MYPROJECT     # Clear data
dku dataset delete old_dataset -P MYPROJECT   # Delete
```

### `dku recipe`

```bash
dku recipe list -P MYPROJECT                  # List recipes
dku recipe create transform --type python --input raw_data --output clean_data -P MYPROJECT
dku recipe get my_recipe -P MYPROJECT         # Recipe details
dku recipe set-code transform --code @transform.py -P MYPROJECT
dku recipe get-code transform -P MYPROJECT    # Print code to stdout
dku recipe get-code transform -P MYPROJECT -o json
dku recipe run my_recipe --wait               # Run and wait
dku recipe add-input my_recipe --ref extra_ds -P MYPROJECT
dku recipe add-output my_recipe --ref result_ds -P MYPROJECT
dku recipe set-definition my_recipe --definition @def.json -P MYPROJECT
dku recipe check-schema my_recipe -P MYPROJECT    # Preview schema updates
dku recipe apply-schema my_recipe -P MYPROJECT    # Apply schema updates
dku recipe create-llm-eval rag_eval --input qa_data --eval-store eval_store_1 --output eval_scored --output-metrics eval_metrics -P MYPROJECT
dku recipe create-agent-eval agent_eval --input agent_runs --eval-store agent_store_1 --output eval_out --output-metrics eval_metrics -P MYPROJECT
dku recipe delete my_recipe -P MYPROJECT      # Delete
```

For `dku recipe create-llm-eval` and `dku recipe create-agent-eval`, any dataset passed with `--output` or `--output-metrics` must already exist in DSS. The CLI validates that upfront and fails directly if those datasets are missing.

### `dku scenario`

```bash
dku scenario list -P MYPROJECT                # List scenarios
dku scenario create daily_build -P MYPROJECT  # Create
dku scenario run my_scenario --wait           # Run and wait
dku scenario abort my_scenario -P MYPROJECT   # Abort running
dku scenario status my_scenario -P MYPROJECT  # Recent runs
dku scenario get-definition my_scenario -P MYPROJECT
dku scenario get-definition my_scenario -P MYPROJECT -o json
dku scenario set-definition my_scenario -P MYPROJECT --definition @def.json
dku scenario delete my_scenario -P MYPROJECT  # Delete
```

### `dku job`

```bash
dku job list -P MYPROJECT                     # List recent jobs
dku job run --target my_dataset -P MYPROJECT  # Build target(s)
dku job run --target ds1 --target ds2 --wait  # Build multiple + wait
dku job status JOB_ID -P MYPROJECT            # Job details
dku job log JOB_ID -P MYPROJECT               # View job log
dku job abort JOB_ID -P MYPROJECT             # Abort job
dku job wait JOB_ID -P MYPROJECT --timeout 300  # Wait with timeout
```

### `dku library`

```bash
dku library list -P MYPROJECT                 # List files
dku library write python/utils/helpers.py --content @helpers.py -P MYPROJECT
dku library read python/utils/helpers.py -P MYPROJECT   # Print to stdout
dku library mkdir python/utils -P MYPROJECT   # Create directory
dku library delete python/utils/old.py -P MYPROJECT
```

### `dku agent`

```bash
dku agent list -P MYPROJECT                   # List agents
dku agent create my_agent --type TOOLS_USING_AGENT -P MYPROJECT
dku agent get my_agent -P MYPROJECT           # Settings
dku agent add-tool my_agent --tool tool1 -P MYPROJECT
dku agent set-llm my_agent --llm-id llm1 -P MYPROJECT
dku agent wake-up my_agent -P MYPROJECT       # Start
dku agent shutdown my_agent -P MYPROJECT      # Stop
dku agent status my_agent -P MYPROJECT        # Check state
dku agent delete my_agent -P MYPROJECT        # Delete
```

### `dku agent-tool`

```bash
dku agent-tool list -P MYPROJECT              # List tools
dku agent-tool get tool1 -P MYPROJECT         # Tool settings
dku agent-tool run tool1 --input '{"query":"..."}' -P MYPROJECT
dku agent-tool delete tool1 -P MYPROJECT      # Delete
```

### `dku knowledge`

```bash
dku knowledge list -P MYPROJECT               # List knowledge banks
dku knowledge create my_kb -P MYPROJECT       # Create
dku knowledge get my_kb -P MYPROJECT          # Settings
dku knowledge build my_kb --wait -P MYPROJECT # Build and wait
dku knowledge search my_kb --query "revenue" -P MYPROJECT
dku knowledge delete my_kb -P MYPROJECT       # Delete
```

`dku knowledge get` expects JSON from the DSS API. On getitstarted instances, the sleep/wake page can intercept the request and return HTML instead. When that happens, the CLI fails explicitly and tells you to wake the instance in the browser before retrying.

### `dku llm`

```bash
dku llm list -P MYPROJECT                     # List completion LLMs
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P MYPROJECT
dku llm completion LLM_ID "Summarize this" -P MYPROJECT
dku llm completion LLM_ID "Extract entities" --system "You are a NER model" --json-output
dku llm embeddings LLM_ID --text "sample text" -P MYPROJECT
```

`dku llm list` defaults to `GENERIC_COMPLETION`. `dku llm embeddings` only accepts LLM IDs available for `TEXT_EMBEDDING_EXTRACTION` in the target project. Use `dku llm list --purpose TEXT_EMBEDDING_EXTRACTION` to find a compatible model.

### `dku bundle`

```bash
dku bundle list -P MYPROJECT                  # List bundles
dku bundle export v1 -P MYPROJECT             # Create snapshot
dku bundle download v1 --dest ./bundles -P MYPROJECT
dku bundle import ./bundle.zip -P MYPROJECT   # Import archive
dku bundle activate v1 -P MYPROJECT           # Activate
```

### `dku api-service`

```bash
dku api-service list -P MYPROJECT             # List services
dku api-service create my_api -P MYPROJECT    # Create
dku api-service get my_api -P MYPROJECT       # Settings
dku api-service create-package my_api -P MYPROJECT
dku api-service list-packages my_api -P MYPROJECT
```

### `dku wiki`

```bash
dku wiki list -P MYPROJECT                    # List articles
dku wiki create "Setup Guide" --body @guide.md -P MYPROJECT
dku wiki get ARTICLE_ID -P MYPROJECT          # Read article
```

### `dku sql`

```bash
dku sql query "SELECT * FROM users LIMIT 10" --connection my_pg
dku sql query @query.sql --connection my_pg   # From file
```

### `dku flow`

```bash
dku flow graph -P MYPROJECT                   # Flow graph summary
dku flow graph -P MYPROJECT -o json           # Full graph as JSON
dku flow visualize -P MYPROJECT               # Render flow as ASCII DAG tree
dku flow zones -P MYPROJECT                   # List zones
dku flow create-zone "Staging" -P MYPROJECT   # Create zone
dku flow propagate ds1 -P MYPROJECT           # Schema propagation from dataset
dku flow check -P MYPROJECT                   # Consistency check
dku flow sources -P MYPROJECT                 # Find root datasets
dku flow successors ds1 -P MYPROJECT          # Downstream nodes
```

### `dku plugin`

```bash
dku plugin list                               # List plugins
dku plugin push ./my-plugin.zip               # Upload plugin
dku plugin settings my-plugin                 # View settings
dku plugin settings my-plugin --set k=v       # Update setting
```

### `dku code-env`

```bash
dku code-env list                             # List code environments
dku code-env get py39                         # Code env details
dku code-env create my-env                    # Create new code env
dku code-env delete py39                      # Delete code env
dku code-env update py39                      # Update packages
```

### `dku connection`

```bash
dku connection list                           # List connections (admin)
dku connection create my_pg --type PostgreSQL --definition @conn.json
dku connection test my_connection             # Test a connection
```

### `dku user`

```bash
dku user list                                 # List DSS users
dku user create jdoe --display-name "John Doe" --email john@example.com
```

### `dku model`

```bash
dku model list -P MYPROJECT                   # List saved models
dku model get MODEL_ID -P MYPROJECT           # Model details
dku model versions MODEL_ID -P MYPROJECT      # List model versions
```

### `dku folder`

```bash
dku folder list -P MYPROJECT                  # List managed folders
dku folder ls FOLDER_ID -P MYPROJECT          # List folder contents
dku folder upload FOLDER_ID ./data.csv -P MYPROJECT
dku folder download FOLDER_ID /data.csv -P MYPROJECT
```

### `dku webapp`

```bash
dku webapp list -P MYPROJECT                  # List web apps
dku webapp start WEBAPP_ID -P MYPROJECT       # Start backend
dku webapp stop WEBAPP_ID -P MYPROJECT        # Stop backend
dku webapp status WEBAPP_ID -P MYPROJECT      # Check status
```

### `dku macro`

```bash
dku macro list -P MYPROJECT                   # List macros
dku macro run MACRO_ID -P MYPROJECT           # Run macro
dku macro run MACRO_ID --params '{"key":"value"}' --wait
```

### `dku config`

```bash
dku config set default_project MYPROJECT      # Set default project
dku config get default_project                # Get config value
dku config set output json                    # Set default output format
dku config list                               # Show all config
dku config path                               # Print config file path
dku config variables                          # Instance-level variables
dku config set-variables --set key=value      # Set instance variables
```

### `dku whoami`

```bash
dku whoami    # ◆ chris on https://dss.example.com (DSS 14.0.2) [admin]
```
