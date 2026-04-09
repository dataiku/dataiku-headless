# Dataiku Scenarios & Automation

Build automated data pipelines and orchestration workflows using Dataiku's scenario framework.

## Overview

Scenarios are the primary automation mechanism in Dataiku DSS. They define **when** something should happen (triggers), **what** should happen (steps), and **who should be notified** (reporters).

### Scenario Types

| Type | Description | Use When |
|------|-------------|----------|
| **Step-based** | Visual sequence of predefined steps | Standard builds, metrics, notifications |
| **Custom Python** | Full Python script with scenario API | Complex logic, conditional branching, API calls |

## Triggers

Triggers define when a scenario starts. Multiple triggers can be added — any matching trigger fires the scenario.

### Time-Based Triggers

```
# Run every day at 2 AM
Type: Time-based
Frequency: Every day
Time: 02:00

# Run every hour on weekdays
Type: Time-based
Frequency: Every 1 hour
Days: Monday-Friday

# Run on the 1st and 15th of each month
Type: Time-based
Frequency: Monthly
Days of month: 1, 15
Time: 06:00
```

### Dataset Change Trigger

Fires when a dataset's data is modified (new records, schema change).

```
Type: Dataset change
Dataset: my_input_dataset
Check every: 5 minutes
```

### SQL Query Trigger

Fires when a SQL query returns results (non-empty result set).

```sql
SELECT COUNT(*) as cnt FROM staging_table
WHERE created_at > '${scenarioTriggerPreviousFireDate}'
AND processed = false
HAVING COUNT(*) > 0
```

### Custom Python Trigger

```python
from dataiku.scenario import Trigger

t = Trigger()

import requests
response = requests.get("https://api.example.com/status")
if response.json().get("new_data_available"):
    t.fire()
```

### Trigger JSON Structures

Use these with `dku scenario add-trigger --trigger '<JSON>'` or `dku scenario set-definition`.

**Dataset change (`ds_modified`)**  — fires when dataset data is modified:
```json
{
  "active": true,
  "type": "ds_modified",
  "delay": 900,
  "graceDelaySettings": {
    "delay": 120,
    "checkAgainAfterGraceDelay": true
  },
  "params": {
    "watches": [{"type": "DATASET", "itemId": "DATASET_NAME"}]
  }
}
```
- `delay`: check interval in seconds (900 = 15 min) — **root level, NOT inside params**
- `graceDelaySettings`: **root level** — seconds to wait after change detected before firing
- `watches`: inside `params` — list of items to watch (`DATASET`, `MANAGED_FOLDER`, `SAVED_MODEL`)
- Shortcut: `dku scenario add-trigger-dataset SCEN --dataset DATASET_NAME -P PROJ`

**Temporal (daily)** — time-based schedule:
```json
{
  "active": true,
  "type": "temporal",
  "params": {
    "frequency": "Daily",
    "hour": 2,
    "minute": 0,
    "repeatFrequency": 1,
    "timezone": "SERVER"
  }
}
```
- `frequency`: `Minutely`, `Hourly`, `Daily`, `Weekly`, `Monthly`
- `Weekly` adds `"daysOfWeek": ["Monday", "Wednesday", "Friday"]`
- `Monthly` adds `"monthlyRunOn": "ON_THE_DAY"` (or `LAST_DAY_OF_THE_MONTH`, `FIRST_WEEK`, etc.)

**SQL query (`sql_query`)** — fires when query returns results:
```json
{
  "active": true,
  "type": "sql_query",
  "params": {
    "connection": "CONNECTION_NAME",
    "query": "SELECT 1 WHERE EXISTS (SELECT * FROM table WHERE processed = false)"
  }
}
```

**Custom Python (`custom_python`)** — fires from Python script using `Trigger().fire()`:
```json
{
  "active": true,
  "type": "custom_python",
  "params": {}
}
```

## Steps

### Build Dataset Step

```
Type: Build / Train
Dataset: my_output_dataset
Build mode: Non-recursive (only this dataset)
             Recursive (rebuild upstream too)
             Smart reconstruction (only rebuild stale)
```

### Execute Python Step

```python
from dataiku.scenario import Scenario

s = Scenario()

# Build a dataset programmatically
s.build_dataset("my_dataset")

# Build with specific partitions
s.build_dataset("partitioned_dataset", partitions="2024-01-15")

# Train a saved model (model ID from URL)
s.train_model("A2B3c4D5")

# Get trigger parameters
trigger_params = s.get_trigger_params()
trigger_type = trigger_params.get("triggerType")
trigger_name = trigger_params.get("triggerName")
```

### Set Project Variables Step

```python
import dataiku

project = dataiku.api_client().get_default_project()

variables = project.get_variables()
standard_vars = variables["standard"]
local_vars = variables["local"]

standard_vars["last_run_date"] = "2024-01-15"
standard_vars["run_count"] = standard_vars.get("run_count", 0) + 1

variables["standard"] = standard_vars
project.set_variables(variables)
```

### Run Other Scenario Step

```
Type: Run scenario
Scenario: downstream_scenario
Wait for completion: Yes / No
Fail if scenario fails: Yes / No
```

### Execute SQL Step

```sql
TRUNCATE TABLE staging_table;

UPDATE orders SET processed = true
WHERE order_date = '${projectVariables.current_date}';
```

### Compute Metrics Step

```
Type: Compute metrics
Dataset: my_output_dataset
Metrics: Record count, column stats, custom metrics
```

### Check Step

```
Type: Run checks
Dataset: my_output_dataset
Checks:
  - Record count > 0 (ERROR if fails)
  - Column "amount" avg between 10 and 1000 (WARNING)
  - No null values in "customer_id" (ERROR)
```

## Reporters

### Email Reporter

```
Send to: team@company.com
Condition: On failure
Subject: [DSS] Scenario ${scenarioName} FAILED
Body: Scenario ${scenarioName} failed at ${currentDate}.
      Error: ${scenarioError}
```

### Webhook Reporter

```
URL: https://hooks.slack.com/services/T00/B00/xxx
Method: POST
Condition: On completion (success or failure)
Body:
{
  "text": "Scenario ${scenarioName}: ${scenarioOutcome}",
  "channel": "#data-alerts"
}
```

### Available Reporter Variables

| Variable | Description |
|----------|-------------|
| `${scenarioName}` | Name of the scenario |
| `${scenarioOutcome}` | SUCCESS, FAILED, ABORTED |
| `${scenarioError}` | Error message if failed |
| `${currentDate}` | Current timestamp |
| `${projectKey}` | Project identifier |
| `${scenarioTriggerName}` | Which trigger fired |

## Metrics & Checks Integration

### Custom Metrics (Python Probes)

```python
import dataiku
from dataiku.custommetrics import *

dataset = dataiku.Dataset("my_dataset")
df = dataset.get_dataframe()

report = MetricReport()
report.add_metric("null_ratio", df["important_col"].isnull().mean())
report.add_metric("distinct_count", df["category"].nunique())
report.add_metric("total_amount", df["amount"].sum())
return report
```

### Custom Python Check

```python
from dataiku.customcheck import *

def check(dataset, config):
    df = dataset.get_dataframe()

    null_pct = df["critical_column"].isnull().mean()

    if null_pct > 0.05:
        return CheckResult(CheckResult.ERROR,
                          f"Null rate {null_pct:.1%} exceeds 5% threshold")
    elif null_pct > 0.01:
        return CheckResult(CheckResult.WARNING,
                          f"Null rate {null_pct:.1%} approaching threshold")
    else:
        return CheckResult(CheckResult.OK,
                          f"Null rate {null_pct:.1%} is acceptable")
```

## Common Patterns

### Pattern 1: Daily Retrain-and-Deploy

```python
from dataiku.scenario import Scenario
import dataiku

s = Scenario()

s.build_dataset("feature_store")
s.train_model("prediction_model_id")

project = dataiku.api_client().get_default_project()
model = project.get_saved_model("prediction_model_id")
active_version = model.get_active_version()
metrics = active_version.get_performance_metrics()

auc = metrics.get("auc")
if auc < 0.75:
    raise Exception(f"Model AUC {auc} below threshold 0.75, skipping deploy")

s.build_dataset("scored_output")
```

### Pattern 2: Data Freshness Monitoring

```python
from dataiku.scenario import Scenario
import dataiku
from datetime import datetime, timedelta

s = Scenario()

dataset = dataiku.Dataset("source_data")
df = dataset.get_dataframe(columns=["updated_at"], limit=1, sampling="head")

last_update = pd.to_datetime(df["updated_at"].max())
hours_stale = (datetime.now() - last_update).total_seconds() / 3600

if hours_stale > 24:
    raise Exception(f"Data is {hours_stale:.0f}h stale (>24h threshold)")

s.build_dataset("processed_output")
```

### Pattern 3: Conditional Branching

```python
from dataiku.scenario import Scenario
import dataiku

s = Scenario()

vars = dataiku.get_custom_variables(typed=True)
mode = vars.get("pipeline_mode", "incremental")

if mode == "full_refresh":
    s.build_dataset("raw_data", build_mode="RECURSIVE")
    s.build_dataset("final_output", build_mode="RECURSIVE")
elif mode == "incremental":
    s.build_dataset("final_output", build_mode="NON_RECURSIVE")
else:
    raise ValueError(f"Unknown pipeline_mode: {mode}")

project = dataiku.api_client().get_default_project()
variables = project.get_variables()
variables["standard"]["last_run_mode"] = mode
variables["standard"]["last_run_timestamp"] = str(datetime.now())
project.set_variables(variables)
```

### Pattern 4: Error Handling with Retry

```python
from dataiku.scenario import Scenario
import time

s = Scenario()

max_retries = 3
for attempt in range(max_retries):
    try:
        s.build_dataset("api_sourced_dataset")
        break
    except Exception as e:
        if attempt < max_retries - 1:
            wait_time = 60 * (2 ** attempt)  # Exponential backoff
            print(f"Attempt {attempt+1} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
        else:
            raise Exception(f"Failed after {max_retries} attempts: {e}")

s.build_dataset("processed_output")
```

### Pattern 5: Multi-Scenario Orchestration

```
Master Scenario (daily 2 AM):
  ├── Step 1: Run "ingest-scenario" (wait=True)
  ├── Step 2: Run "transform-scenario" (wait=True)
  ├── Step 3: Run "model-retrain-scenario" (wait=True)
  ├── Step 4: Run "export-scenario" (wait=True)
  └── Reporter: Email on failure

Each sub-scenario:
  - Has its own error handling
  - Reports independently
  - Can be run standalone for debugging
```

## Best Practices

### Design
- **One scenario per pipeline** — don't overload a single scenario
- **Use project variables** for configuration (thresholds, dates, modes)
- **Chain scenarios** via "Run scenario" steps for complex orchestration
- **Name clearly** — include frequency and purpose (e.g., "Daily - Retrain Models")

### Error Handling
- **Set meaningful timeouts** on build steps (default is no timeout)
- **Add checks after critical builds** to catch data quality issues early
- **Use reporters on failure** — always know when something breaks
- **Log context** in Python steps for debugging (`print()` goes to scenario log)

### Performance
- **Use "Smart reconstruction"** build mode to skip up-to-date datasets
- **Avoid "Recursive" builds** unless you need a full refresh
- **Stagger scenario schedules** to avoid resource contention
- **Set partition ranges** for partitioned builds instead of building all

### Monitoring
- **Check scenario run history** regularly for timing trends
- **Set up alerts** for scenarios that exceed expected duration
- **Use metrics + checks** as automated data quality gates
- **Track project variables** to maintain audit trail of pipeline state
