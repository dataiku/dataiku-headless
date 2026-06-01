# Workflow Templates

Task-specific copy-paste templates. Generic inspect, build, chaining, and verification guidance lives in `recipe-operations.md`.

## Reference Map

| Need | Read |
|---|---|
| Generic inspect/gauge/sample/build/verify | `recipe-operations.md` |
| Exact flags | `commands.md` |
| Operational traps | `common-gotchas.md` |
| Safety confirmations | `safety.md` |

## Data Pipeline

```bash
dku project create MY_PROJ --name "My Project" --if-not-exists && \
dku dataset create raw_data --type UploadedFiles -P MY_PROJ && \
dku dataset upload raw_data data.csv -P MY_PROJ --overwrite && \
dku dataset create lookups --type UploadedFiles -P MY_PROJ && \
dku dataset upload lookups lookups.csv -P MY_PROJ --overwrite && \
dku recipe create-join enrich -i raw_data -i lookups --output-ds enriched --join-key id -P MY_PROJ && \
dku recipe create-group summarize -i enriched --output-ds summary -k category --agg "amount:sum,avg" -P MY_PROJ && \
dku job run --target summary -P MY_PROJ --type RECURSIVE_BUILD --auto-update-schema --wait && \
dku dataset head summary -P MY_PROJ -n 5
```

## Agent And Knowledge Bank

```bash
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P MY_PROJ -o json | jq -r '.[0].id'

dku agent create support_agent -P MY_PROJ && \
dku agent set-llm support_agent --llm-id openai:gpt-4o -P MY_PROJ && \
dku knowledge create support_kb --embedding-llm "openai:conn:text-embedding-3-small" -P MY_PROJ && \
dku knowledge build support_kb -P MY_PROJ --wait && \
dku knowledge search support_kb --query "test query" -P MY_PROJ
```

## Visual ML

```bash
# Create ML task on dataset
dku ml create-prediction customers churn --type BINARY_CLASSIFICATION -P MY_PROJ -o json

# Explore and configure algorithms
dku ml algorithms ANALYSIS_ID MLTASK_ID -P MY_PROJ
dku ml set-algorithm ANALYSIS_ID MLTASK_ID --disable-all --enable XGBoost --enable RandomForest -P MY_PROJ

# Train (creates a training session with multiple model candidates)
dku ml train ANALYSIS_ID MLTASK_ID -P MY_PROJ -o json

# Inspect results, then iterate (change settings, re-train)
dku ml details ANALYSIS_ID MLTASK_ID MODEL_ID -P MY_PROJ

# Deploy to Flow as a saved model
dku ml deploy ANALYSIS_ID MLTASK_ID MODEL_ID --name ChurnModel --train-dataset customers -P MY_PROJ
dku model metrics DEPLOYED_MODEL_ID -P MY_PROJ

# Later iteration: update existing saved model with new version
dku ml deploy ANALYSIS_ID MLTASK_ID NEW_MODEL_ID --name ChurnModel \
  --train-dataset customers -P MY_PROJ \
  --saved-model-id DEPLOYED_MODEL_ID
# This creates a new version in the existing saved model (preserves downstream refs)
```

## Job Recovery

When a build, run, or training call times out before reaching a terminal state:

```bash
# 1. Check job status -- timeout is NOT failure
dku job list -P PROJ -o json

# 2. Wait for the specific job to complete
dku job wait JOB_ID -P PROJ

# 3. Check logs on failure
dku job log JOB_ID -P PROJ

# 4. Verify outputs -- a completed job may have partial results
dku dataset head TARGET -P PROJ -n 5
dku dataset info TARGET -P PROJ --recompute
```

**Rules:**
- Timeout is not failure. A timed-out wait means the job may still be queued or running.
- Do not start another overlapping build/run on the same recipe, output, or downstream path while a prior job may still be active.
- Do not assume a missing job_id means the job is gone -- use `dku job list` to rediscover recent project jobs.
- For linearly dependent recipes: complete the full cycle (create, configure, run, verify) for each recipe before starting the next. Never batch-create multiple dependent recipes and run them all at once.

## Deployment

```bash
dku bundle export v1 -P MY_PROJ && \
dku bundle download v1 -P MY_PROJ --dest ./bundles
```

```bash
dku plugin push plugin.zip --install && \
dku plugin create-code-env my-plugin && \
dku plugin set-code-env my-plugin plugin_my_plugin_managed && \
dku plugin get my-plugin -o json
```

## Documentation

```bash
dku project set-metadata MY_PROJ --description "Customer churn analytics: joins customer data with events, computes risk features, and summarizes by segment." && \
dku dataset set-column-description customers \
  customer_id "Unique customer identifier" \
  monthly_spend "Monthly subscription amount in USD" \
  tenure_months "Months since customer signup" \
  -P MY_PROJ && \
dku wiki create "Project Overview" --body "# Customer Churn Analytics\n\nPipeline that identifies at-risk customers using behavioral features." --if-not-exists -P MY_PROJ
```

## Task-Specific Verification

```bash
# Agents
dku agent status AGENT_NAME -P PROJ && \
dku agent-tool list -P PROJ -o json

# Knowledge Banks
dku knowledge build KB_NAME -P PROJ --wait && \
dku knowledge search KB_NAME --query "test query" -P PROJ

# Semantic Models
dku semantic-model get-version SM_ID -P PROJ -o json && \
dku semantic-model update-index SM_ID --wait -P PROJ
```
