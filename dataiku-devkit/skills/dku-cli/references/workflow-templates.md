# Workflow Templates & Chaining Patterns

Copy-paste-ready templates for common multi-step workflows. All examples use `&&`-chaining in a single Bash tool call.

## CSV Upload: fix the STRING-typed schema

`dataset upload` on a CSV auto-detects format but leaves every column typed as
`string`. Any downstream numeric/date recipe (ML, Prepare DateParser, filter
on numeric range) will fail or silently coerce. Apply a typed schema BEFORE
wiring recipes:

```bash
dku dataset upload raw data.csv -P PROJ && \
dku dataset set-schema raw -d @schema.json -P PROJ && \
dku dataset head raw -P PROJ -n 5   # verify typed values
```

Generate a schema stub with `dku dataset detect DS -P PROJ -o json` and edit
types as needed.

## JSON piping: don't `2>&1`

`dku` writes status lines like `◆ Deployed to flow. Saved model: ...` to
**stderr**; JSON payloads go to stdout. Piping `2>&1` into `jq` mixes them and
produces a parse error. Instead:

```bash
# CORRECT — stderr passes through to the terminal, jq reads clean JSON
dku ml deploy MODEL_ID --name my_model -P PROJ -o json | jq .saved_model_id

# WRONG — 2>&1 corrupts jq's input
dku ml deploy MODEL_ID --name my_model -P PROJ -o json 2>&1 | jq .   # parse error
```

## ML training: audit `settings` for label leakage

After `dku ml create-prediction`, the auto-guesser sets feature roles but does
not detect label leakage (e.g. a `true_label` column kept as INPUT). Silent
AUC≈1.0 models are the worst kind of failure. Audit and reject leaky columns
BEFORE training:

```bash
# 1. Create the task
dku ml create-prediction customer_features churn -P PROJ
# → returns {analysis_id, mltask_id}

# 2. Audit which columns are INPUT
dku ml settings ANALYSIS MLTASK -P PROJ | jq '.preprocessing.per_feature | to_entries | map({col: .key, role: .value.role})'

# 3. Reject anything that leaks the target
dku ml set-feature ANALYSIS MLTASK true_label --role REJECT -P PROJ
dku ml set-feature ANALYSIS MLTASK event_after_churn --role REJECT -P PROJ

# 4. Train
dku ml train ANALYSIS MLTASK -P PROJ --wait
```

## Multi-Dataset Project (e-commerce example)

```bash
# Create project + 3 datasets + upload — ALL ONE CALL
dku project create ECOM --name "E-Commerce" --if-not-exists && \

# Generate CSVs
cat > /tmp/customers.csv << 'EOF'
customer_id,name,email,country
C001,Alice,alice@ex.com,France
C002,Bob,bob@ex.com,USA
EOF

cat > /tmp/orders.csv << 'EOF'
order_id,customer_id,product,quantity,price
O001,C001,Widget,2,29.99
O002,C002,Gadget,1,49.99
EOF

# Create all as UploadedFiles (required for upload)
dku dataset create customers --type UploadedFiles -P ECOM && \
dku dataset create orders --type UploadedFiles -P ECOM && \

# Upload all
dku dataset upload customers /tmp/customers.csv -P ECOM && \
dku dataset upload orders /tmp/orders.csv -P ECOM
```

## Full Project Template (3 Tool Calls)

This template covers the complete lifecycle: setup, build, and extras.

**Tool call 1 — Wire everything:**

```bash
# Create project (--if-not-exists = idempotent, safe to re-run)
dku project create MY_PROJ --name "My Project" --if-not-exists && \

# Upload source data (UploadedFiles for CSV upload)
dku dataset create raw_data --type UploadedFiles -P MY_PROJ && \
dku dataset upload raw_data /tmp/data.csv -P MY_PROJ && \

# Recipe 1: raw_data + lookup → enriched (VISUAL join — not Python)
dku recipe create-join join_enriched -i raw_data -i lookup --output-ds enriched --join-key id -P MY_PROJ && \

# Recipe 2: enriched → summary (VISUAL group — not Python)
dku recipe create-group compute_summary -i enriched --output-ds summary -k category --agg "amount:sum,avg" -P MY_PROJ && \

# Recipe 3: summary → scored (Python — ONLY because custom scoring logic)
dku recipe create compute_scored --type python --input summary --output-ds scored -P MY_PROJ && \
dku recipe set-code compute_scored -P MY_PROJ --code @score.py && \

# Library files
dku library write python/utils/helpers.py -P MY_PROJ --content @helpers.py && \

# Project variables
dku project set-variables -P MY_PROJ --set threshold=0.8 --set env=staging && \

# Scenario with dataset change trigger
dku scenario create daily_build --if-not-exists -P MY_PROJ && \
dku scenario add-trigger-dataset daily_build --dataset raw_data -P MY_PROJ && \

# Wiki (--if-not-exists = safe to re-run)
dku wiki create "Project Overview" --body "# My Project\nAutomated data pipeline." --if-not-exists -P MY_PROJ && \

# Document the project (descriptions, column docs)
dku project set-metadata MY_PROJ --description "Automated data pipeline — enriches raw data, computes summary statistics, scores items." && \
dku dataset set-column-description raw_data id "Unique record ID" name "Item name" amount "Transaction amount in USD" -P MY_PROJ && \
dku scenario set-metadata daily_build --description "Nightly rebuild of the full pipeline" -P MY_PROJ
```

**Tool call 2 — Build the pipeline:**

```bash
dku job run --target scored -P MY_PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait
```

**Tool call 3 — Verify (MANDATORY — never skip this):**

```bash
# Check final output has real data (not empty)
dku dataset head scored -P MY_PROJ -n 5 && \
# Check pipeline topology is correct
dku flow graph -P MY_PROJ -o json | jq '.nodes | keys' && \
# Check row count is reasonable
dku dataset head scored -P MY_PROJ -o json | jq 'length'
```

> **You are NOT done until Tool call 3 passes.** If `head` returns 0 rows or wrong columns, debug before reporting success.

## Pipeline Building — Wire First, Build Once

### Anti-Pattern: Step-by-Step Builds

```bash
# BAD — each build is non-recursive, no schema updates.
# If schemas don't match between steps, every downstream build fails.
dku dataset build ds_a -P PROJ --wait && \
dku dataset build ds_b -P PROJ --wait && \
dku dataset build ds_c -P PROJ --wait
```

### Correct Pattern

**Step 1:** Wire the entire pipeline (datasets + recipes) in one `&&` chain. Visual recipe commands auto-create managed output datasets.

**Step 2:** Build with auto-schema (one command):

```bash
dku job run --target FINAL_OUTPUT -P PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait
```

### Build Types

| Type | Behavior |
|---|---|
| `NON_RECURSIVE_FORCED_BUILD` | Build only specified outputs (default) |
| `RECURSIVE_BUILD` | Build outputs + upstream dependencies that need building |
| `RECURSIVE_FORCED_BUILD` | Force-rebuild outputs + ALL upstream dependencies |
| `RECURSIVE_MISSING_ONLY_BUILD` | Build only outputs that have never been built |

### When to Use What

| Scenario | Command |
|---|---|
| Build one dataset (schema already correct) | `dku dataset build NAME --wait` |
| Build entire pipeline from leaf dataset | `dku job run --target NAME --type RECURSIVE_BUILD --auto-update-schema --wait` |
| Schema changed on source, propagate downstream | `dku flow propagate SOURCE_DS -P PROJ` |
| Check if a recipe's output schema is stale | `dku recipe check-schema RECIPE -P PROJ` |
| Apply pending schema updates for a recipe | `dku recipe apply-schema RECIPE -P PROJ` |
| Run consistency check on entire flow | `dku flow check -P PROJ` |
| Force rebuild everything | `dku job run --target NAME --type RECURSIVE_FORCED_BUILD --auto-update-schema --wait` |
| Build only missing outputs | `dku job run --target NAME --type RECURSIVE_MISSING_ONLY_BUILD --wait` |
| Build recipe that outputs to a managed folder | `dku recipe run RECIPE -P PROJ --wait` (folders NOT buildable via `dataset build`) |
| Inspect a failed build log | `dku job log JOB_ID -P PROJ` |

## Chaining Pattern Examples

### Data Pipeline (1 tool call)

```bash
# Project + datasets + visual recipes + build — all one call
dku project create MY_PROJ --name "My Project" --if-not-exists && \
dku dataset create raw_data --type UploadedFiles -P MY_PROJ && \
dku dataset upload raw_data data.csv -P MY_PROJ && \
dku dataset create lookups --type UploadedFiles -P MY_PROJ && \
dku dataset upload lookups lookups.csv -P MY_PROJ && \
dku recipe create-join enrich -i raw_data -i lookups --output-ds enriched -P MY_PROJ && \
dku recipe create-group summarize -i enriched --output-ds summary -k category -P MY_PROJ && \
dku scenario create daily_build -P MY_PROJ
```

### Agent + Knowledge Bank (1 tool call)

```bash
# First, find an embedding model for the knowledge bank
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P MY_PROJ -o json | jq -r '.[0].id'

# Create agent with tools and knowledge — all one call
dku agent create my_agent -P MY_PROJ && \
dku agent set-llm my_agent --llm-id openai:gpt-4o -P MY_PROJ && \
dku knowledge create my_kb --embedding-llm "openai:conn:text-embedding-3-small" -P MY_PROJ && \
dku knowledge build my_kb -P MY_PROJ --wait && \
dku agent add-tool my_agent --tool my_tool -P MY_PROJ
```

### ML Pipeline (1 tool call)

```bash
# Create prediction task, train, deploy to flow — all one call
dku ml create-prediction customers churn --type BINARY_CLASSIFICATION -P MY_PROJ -o json && \
dku ml train ANALYSIS_ID MLTASK_ID -P MY_PROJ -o json && \
dku ml deploy ANALYSIS_ID MLTASK_ID MODEL_ID --name ChurnModel --train-dataset customers -P MY_PROJ
```

**Typical ML workflow:**
1. `dku ml create-prediction DS TARGET -P PROJ` — creates analysis + ML task, returns `analysis_id` and `mltask_id`
2. `dku ml algorithms AID TID -P PROJ` — see available/enabled algorithms
3. `dku ml set-algorithm AID TID --disable-all --enable XGBoost --enable RandomForest -P PROJ` — tune algorithms
4. `dku ml train AID TID -P PROJ` — train and get model IDs
5. `dku ml details AID TID MODEL_ID -P PROJ` — check metrics
6. `dku ml deploy AID TID MODEL_ID --name MyModel --train-dataset DS -P PROJ` — deploy to flow
7. `dku model set-active-version MODEL_ID VERSION_ID -P PROJ` — activate specific version
8. `dku model metrics MODEL_ID -P PROJ` — check deployed model metrics

### Deploy (1 tool call)

```bash
# Export + download bundle — all one call
dku bundle export v1 -P MY_PROJ && \
dku bundle download v1 -P MY_PROJ --dest ./bundles
```

### Plugin Lifecycle (1 tool call)

```bash
# First install: push + create code env + assign it
dku plugin push plugin.zip --install && \
dku plugin create-code-env my-plugin && \
dku plugin set-code-env my-plugin plugin_my_plugin_managed

# Update: push + rebuild code env (if deps changed)
dku plugin push plugin.zip && \
dku plugin update-code-env my-plugin

# Check plugin state
dku plugin get my-plugin -o json
dku plugin usages my-plugin
```

### Shell Variable Capture

```bash
# When a downstream command needs output from an upstream one
JOB_ID=$(dku dataset build output -P PROJ 2>/dev/null | sed -n 's/.*Job ID: //p') && \
dku job wait "$JOB_ID" -P PROJ --timeout 300
```

### Safe JSON Piping

```bash
# Success path: parse stdout only
dku recipe get my_recipe -P PROJ -o json | jq '.type'

# Failure path: request machine-readable stderr
if ! dku --errors json recipe get missing_recipe -P PROJ -o json >out.json 2>err.json; then
  jq '.error.code, .error.message' err.json
fi
```

## Composability Patterns

```bash
# Get all project keys as plain list
dku project list -o json | jq -r '.[].key'

# Find datasets with "customer" in name
dku dataset list -P PROJ -o json | jq '.[] | select(.name | test("customer"; "i"))'

# Export all projects
for key in $(dku project list -o json | jq -r '.[].key'); do
  dku project export "$key" -d ./exports
done

# Run scenario and check result
dku scenario run BUILD_ALL -P PROJ --wait || echo "Scenario failed"

# List triggers on a scenario
dku scenario list-triggers BUILD_ALL -P PROJ

# Add dataset change trigger (fires when dataset is modified)
dku scenario add-trigger-dataset BUILD_ALL --dataset raw_data -P PROJ

# Add dataset change trigger with custom intervals
dku scenario add-trigger-dataset BUILD_ALL --dataset raw_data --delay 600 --grace-delay 60 -P PROJ

# Add time-based trigger via JSON
dku scenario add-trigger BUILD_ALL --trigger '{"active":true,"type":"temporal","params":{"frequency":"Daily","hour":2,"minute":0,"repeatFrequency":1,"timezone":"SERVER"}}' -P PROJ

# Remove a trigger by index
dku scenario remove-trigger BUILD_ALL --index 0 -P PROJ

# Build dataset in CI (quiet mode, non-interactive)
dku --quiet dataset build output_table -P PROJ --wait

# Dump recipe code to file
dku recipe get-code my_recipe -P PROJ > recipe.py
```

## Multi-Profile Workflow

```bash
# Set up multiple instances
dku auth login --profile dev --url https://dev-dss.example.com --api-key DEV_KEY
dku auth login --profile prod --url https://prod-dss.example.com --api-key PROD_KEY

# Switch context
dku auth switch prod

# Or use per-command override
dku project list --profile dev
dku project list --profile prod

# List profiles
dku auth list
```

### After `dataset build` — detect orphaned recipes

A `dku dataset build` can report success while doing nothing when a recipe
input is silently ignored (e.g. a folder name written as a dataset ref). The
job's source graph is empty, the job exits 0, and the output dataset is
unchanged — there's no surface error.

```bash
# Detect orphaned recipes in the job log
dku job log JOB_ID -P PROJ | grep -E "Failed to add recipe|Job has the following sources: \{\}" || true
```

If either pattern appears, a recipe was silently dropped. Check its inputs:

```bash
dku recipe get-settings SUSPECT_RECIPE -P PROJ -o json | jq '.inputs'
```

Fix folder refs with `dku recipe add-input RECIPE FOLDER_ID --type MANAGED_FOLDER`.

## Task-Specific Verification Blocks

### After Creating Agents

```bash
# Verify agent is alive and has tools attached
dku agent status AGENT_NAME -P PROJ && \
dku agent-tool list -P PROJ -o json | jq '[.[] | select(.agentId == "AGENT_ID")]'
```

### After Creating Knowledge Banks

```bash
# Build and then test search actually returns results
dku knowledge build KB_NAME -P PROJ --wait && \
dku knowledge search KB_NAME --query "test query" -P PROJ
```

### After Configuring Semantic Models

```bash
# Create, configure, index, and verify
dku semantic-model create "Sales Model" -P PROJ && \
dku semantic-model get-version SM_ID -P PROJ -o json  # verify entities exist
dku semantic-model update-index SM_ID --wait -P PROJ   # index distinct values
```

### After Configuring Agent Hub

```bash
# List enterprise agents and verify LLM is set
dku agent-hub list-agents -P PROJ && \
dku agent-hub config -P PROJ -o json | jq '.default_llm_id'
```

## Documentation Code Examples

### Full Documentation Workflow

```bash
# 1. Project description
dku project set-metadata MY_PROJ --description "Customer churn analytics — joins customer data with events, computes risk features, summarizes by segment."

# 2. Column descriptions on key datasets
dku dataset set-column-description customers \
  customer_id "Unique customer identifier" \
  monthly_spend "Monthly subscription amount in USD" \
  tenure_months "Months since customer signup" \
  -P MY_PROJ

# 3. AI-generated descriptions (quick alternative — requires AI Services enabled)
dku dataset ai-describe customers --save -P MY_PROJ

# 4. Wiki overview
dku wiki create "Project Overview" --body "# Customer Churn Analytics\n\nPipeline that identifies at-risk customers using behavioral features.\n\n## Datasets\n- customers: Source customer data\n- events: User activity events\n- churn_features: Computed risk features\n\n## Recipes\n- join_data: Joins customers with events\n- compute_features: Groups and aggregates features\n\n## Schedule\n- daily_build: Runs nightly at 2am UTC" --if-not-exists -P MY_PROJ
```
