---
name: scenario-step-reference
description: Full payload reference for Dataiku scenario step types, trigger types, and reporter (email) configuration. Load this when constructing or editing scenario steps, triggers, or reporters.
---

# Scenario Step, Trigger, and Reporter Reference

## Step Envelope (all step types share these fields)

Every step in `params.steps` has this structure:

```json
{
  "id": "unique_step_id",
  "type": "build_flowitem",
  "name": "human_readable_label",
  "enabled": true,
  "alwaysShowComment": false,
  "runConditionType": "RUN_IF_STATUS_MATCH",
  "runConditionStatuses": ["SUCCESS", "WARNING"],
  "runConditionExpression": "",
  "resetScenarioStatus": false,
  "delayBetweenRetries": 10,
  "maxRetriesOnFail": 0,
  "params": { ... }
}
```

**`runConditionType`** values:
- `RUN_IF_STATUS_MATCH` (default): run if scenario status is in `runConditionStatuses`
- `RUN_ALWAYS`: run regardless of prior step outcomes
- `RUN_CONDITIONALLY`: run if `runConditionExpression` evaluates to true — expressions can reference `stepOutcome_<step_name>` (e.g., `"stepOutcome_loan_default_model == 'SUCCESS'"`)

## Step Type Reference

Each section below shows only the `type`- and `params`-specific fields. Every step must also include all the envelope fields defined above (`id`, `name`, `enabled`, `runConditionType`, etc.).

### `build_flowitem` — Build datasets, models, folders, or other flow items

```json
{
  "type": "build_flowitem",
  "params": {
    "builds": [
      {"type": "DATASET", "itemId": "my_dataset", "partitionsSpec": ""},
      {"type": "SAVED_MODEL", "itemId": "ekrBiSZ4", "partitionsSpec": ""},
      {"type": "MANAGED_FOLDER", "itemId": "rjordojF", "partitionsSpec": ""},
      {"type": "MODEL_EVALUATION_STORE", "itemId": "C8N15baF", "partitionsSpec": ""},
      {"type": "RETRIEVABLE_KNOWLEDGE", "itemId": "o2oAJHaP"},
      {"type": "DATASET", "itemId": "MY_PARTITIONED_DS", "partitionsSpec": "PREVIOUS_MONTH"}
    ],
    "jobType": "RECURSIVE_FORCED_BUILD",
    "autoUpdateSchemaBeforeEachRecipeRun": true,
    "stopAtFlowZoneBoundary": false,
    "refreshHiveMetastore": true,
    "handleWarningsAs": "WARNING",
    "proceedOnFailure": false
  }
}
```

**`jobType`**: `NON_RECURSIVE_FORCED_BUILD` | `RECURSIVE_BUILD` | `RECURSIVE_FORCED_BUILD`

**`partitionsSpec`**: for non-partitioned datasets always use `""`. For partitioned datasets, you must explicitly name the partitions to build — there is no "build all" shorthand:
- Single partition: `"2014-03-01"` (daily), `"2014-03"` (monthly)
- Date range: `"2014-03-01/2014-04-15"` — builds every partition between the two dates (cannot combine with keywords)
- Discrete multi-value: `"partition_1/partition_2/partition_3"`
- Time keywords (replaced at run time by the scheduler):
  - Daily: `CURRENT_DAY`, `PREVIOUS_DAY`
  - Monthly: `CURRENT_MONTH`, `PREVIOUS_MONTH`
  - Hourly: `CURRENT_HOUR`, `PREVIOUS_HOUR`
  - Yearly: `CURRENT_YEAR`, `PREVIOUS_YEAR`

Keywords cannot be combined with the `/` range notation.

### `compute_metrics` — Compute dataset metrics

```json
{
  "type": "compute_metrics",
  "params": {
    "computes": [{"type": "DATASET", "itemId": "my_dataset", "partitionsSpec": ""}],
    "proceedOnFailure": false
  }
}
```

### `check_dataset` — Run data quality checks on a dataset

```json
{
  "type": "check_dataset",
  "params": {
    "checks": [{"type": "DATASET", "itemId": "my_dataset", "partitionsSpec": ""}],
    "handleWarningsAs": "WARNING",
    "computeAutomaticRules": true,
    "ignorePartitionSelectionMode": false,
    "proceedOnFailure": false
  }
}
```

### `check_consistency` — Check flow graph consistency

```json
{
  "type": "check_consistency",
  "params": {
    "handleWarningsAs": "WARNING",
    "proceedOnFailure": false
  }
}
```

**`runConditionType`**: set to `RUN_ALWAYS` so consistency is checked even after prior step failures.

### `custom_python` — Run inline Python code

```json
{
  "type": "custom_python",
  "maxRetriesOnFail": 2,
  "params": {
    "script": "import dataiku\nprint('hello')",
    "envSelection": {"envMode": "INHERIT"},
    "proceedOnFailure": false
  }
}
```

**`envMode`**: `"INHERIT"` uses the default code env; use a named code env to specify one explicitly.

### `exec_sql` — Execute a SQL statement on a connection

```json
{
  "type": "exec_sql",
  "params": {
    "connection": "MY_CONNECTION",
    "sql": "TRUNCATE TABLE staging.my_table",
    "overrideDefaultLimit": false,
    "extraConf": [],
    "proceedOnFailure": false
  }
}
```

### `set_project_vars` — Set project-level variables

```json
{
  "type": "set_project_vars",
  "params": {
    "variables": {"run_date": "2026-01-01", "batch_size": 500},
    "definitions": [],
    "evaluateValues": false
  }
}
```

### `define_vars` — Define scenario-scoped variables (evaluated expressions)

```json
{
  "type": "define_vars",
  "params": {
    "variables": {},
    "definitions": [
      {"secret": false, "key": "my_var", "value": "\"some_string\""},
      {"secret": false, "key": "count", "value": "4"}
    ],
    "evaluateValues": true
  }
}
```

**`evaluateValues`**: set to `true` to evaluate `value` as an expression. Use `define_vars` for computed/dynamic scenario-scoped values; use `set_project_vars` for simple key-value writes to project variables. Variables defined here are available as `${my_var}` in subsequent step params.

### `reload_schema` — Reload schema from source (e.g., after upstream DDL changes)

```json
{
  "type": "reload_schema",
  "params": {
    "items": [{"type": "DATASET", "itemId": "MY_EXTERNAL_TABLE", "partitionsSpec": ""}],
    "proceedOnFailure": false
  }
}
```

### `schema_propagation` — Propagate schema changes downstream through the flow

```json
{
  "type": "schema_propagation",
  "params": {
    "options": {
      "datasetName": "MY_SOURCE_DATASET",
      "behavior": "AUTO_WITH_BUILDS",
      "recipeUpdateOptions": {},
      "partitionByDim": [],
      "partitionByComputable": [],
      "excludedRecipes": ["recipe_to_skip"],
      "markAsOkRecipes": ["recipe_to_mark_ok"]
    },
    "proceedOnFailure": false
  }
}
```

### `refresh_chart_cache` — Refresh chart/explore cache on datasets

```json
{
  "type": "refresh_chart_cache",
  "params": {
    "force": false,
    "dashboards": [],
    "datasets": [{"smartName": "my_dataset", "name": "my_dataset"}],
    "proceedOnFailure": false
  }
}
```

### `create_dashboard_export` — Export a dashboard to a managed folder as PDF

```json
{
  "type": "create_dashboard_export",
  "params": {
    "dashboardId": "j4Ju74P",
    "exportFormat": {
      "paperSize": "A4",
      "orientation": "LANDSCAPE",
      "fileType": "PDF",
      "width": 1754,
      "height": 1240
    },
    "shouldUseDashboardFormatSettings": true,
    "folderSmartId": "zy6wHTMJ",
    "filtersBySlide": [],
    "proceedOnFailure": true
  }
}
```

**`paperSize`**: `"A4"` | `"US_LETTER"` | others.
**`orientation`**: `"LANDSCAPE"` | `"PORTRAIT"`.
**`shouldUseDashboardFormatSettings`**: set to `false` and provide explicit `width`/`height` to override the dashboard's own format settings.

### `create_wiki_export` — Export the project wiki to a managed folder

```json
{
  "type": "create_wiki_export",
  "params": {
    "exportFormat": {"paperSize": "A4"},
    "folderSmartId": "1h34Nj1R",
    "exportType": "WHOLE_WIKI",
    "exportAttachments": true,
    "proceedOnFailure": false
  }
}
```

### `create_saved_model_documentation_export` — Export model documentation to a folder

```json
{
  "type": "create_saved_model_documentation_export",
  "params": {
    "modelId": "ekrBiSZ4",
    "mlTaskType": "PREDICTION",
    "fullModelId": "ACTIVE_VERSION",
    "withTimestamp": true,
    "targetFolderId": "aMTe8oVt",
    "defaultTemplate": true,
    "proceedOnFailure": false
  }
}
```

### `create_flow_documentation_export` — Export flow documentation to a folder

```json
{
  "type": "create_flow_documentation_export",
  "params": {
    "withTimestamp": true,
    "targetFolderId": "hmhJ0dyo",
    "defaultTemplate": true,
    "proceedOnFailure": false
  }
}
```

### `prepare_lambda_package` — Package an API service for deployment

```json
{
  "type": "prepare_lambda_package",
  "params": {
    "serviceId": "my_api_service",
    "packageId": "v",
    "transmogrify": true,
    "targetVariable": "version_id",
    "releaseNotes": "Release notes here",
    "publishToAPIDeployer": true,
    "publishedServiceId": "my_api_service"
  }
}
```

**`targetVariable`**: name of the scenario variable that will receive the new package ID. Reference it in subsequent steps as `${version_id}`.

### `update_apideployer_deployment` — Update an API Deployer deployment to a new package version

```json
{
  "type": "update_apideployer_deployment",
  "params": {
    "isFullUpdate": true,
    "deploymentId": "my-service-on-prod",
    "newVersionId": "${version_id}"
  }
}
```

### `prepare_bundle` — Create a project bundle and optionally publish to the Deployer

```json
{
  "type": "prepare_bundle",
  "params": {
    "bundleId": "v",
    "transmogrify": true,
    "targetVariable": "bundle_id",
    "publishedProjectKey": "MY_PROJECT",
    "publishOnDeployer": true,
    "releaseNotes": "Bundle release notes"
  }
}
```

**`targetVariable`**: name of the scenario variable that will receive the new bundle ID.

### `run_scenario` — Trigger another scenario as a step

```json
{
  "type": "run_scenario",
  "params": {
    "scenarioId": "SOME_OTHER_SCENARIO",
    "handleWarningsAs": "WARNING",
    "proceedOnFailure": false
  }
}
```

### `restart_webapp` — Restart a DSS webapp

```json
{
  "type": "restart_webapp",
  "params": {
    "webAppId": "7Ea7kqp",
    "proceedOnFailure": false
  }
}
```

## Trigger Type Reference

### `temporal` — Time-based schedule

All temporal triggers share the same envelope; `frequency` and `repeatFrequency` determine the cadence.

**Every N hours:**
```json
{
  "type": "temporal", "name": "Every 4 hours", "delay": 5, "active": true,
  "params": {
    "frequency": "Hourly", "repeatFrequency": 4,
    "startingFrom": "2026-01-01", "minute": 0, "hour": 0, "timezone": "SERVER"
  }
}
```

**Daily at a fixed time:**
```json
{
  "type": "temporal", "name": "Daily at 16:00 UTC", "delay": 5, "active": true,
  "params": {
    "frequency": "Daily", "repeatFrequency": 1,
    "startingFrom": "2026-01-01", "hour": 16, "minute": 0, "timezone": "UTC",
    "monthlyRunOn": "ON_THE_DAY"
  }
}
```

**Weekly on specific days:**
```json
{
  "type": "temporal", "name": "Every Monday at 05:00", "delay": 5, "active": true,
  "params": {
    "frequency": "Weekly", "repeatFrequency": 1,
    "startingFrom": "2026-01-01", "daysOfWeek": ["Monday"],
    "hour": 5, "minute": 0, "timezone": "SERVER"
  }
}
```

**Every N months:**
```json
{
  "type": "temporal", "name": "Every 2 months", "delay": 5, "active": true,
  "params": {
    "frequency": "Monthly", "repeatFrequency": 2,
    "startingFrom": "2026-01-01", "monthlyRunOn": "ON_THE_DAY",
    "hour": 21, "minute": 0, "timezone": "SERVER"
  }
}
```

**`frequency`**: `"Hourly"` | `"Daily"` | `"Weekly"` | `"Monthly"`
**`repeatFrequency`**: how many units between runs (1 = every hour/day/week/month; 2 = every other, etc.).
**`timezone`**: `"SERVER"` (DSS server timezone) or any IANA timezone string (e.g., `"UTC"`, `"America/New_York"`).
**`monthlyRunOn`**: `"ON_THE_DAY"` — run on the calendar day from `startingFrom`. Present on Daily and Monthly triggers.

### `ds_modified` — Fire when a dataset is modified

```json
{
  "id": "trigger_id",
  "type": "ds_modified",
  "name": "Dataset modified",
  "delay": 900,
  "active": true,
  "params": {
    "watches": [
      {"type": "DATASET", "itemId": "my_dataset", "partitionsSpec": ""}
    ],
    "triggerWhenAllFire": false
  },
  "graceDelaySettings": {"delay": 120, "checkAgainAfterGraceDelay": true}
}
```

**`delay`** (seconds): how long to wait after detecting the change before firing.
**`graceDelaySettings.delay`**: additional grace period in seconds before the trigger fires.

### `sql_query` — Fire when a SQL query's output changes

```json
{
  "id": "trigger_id",
  "type": "sql_query",
  "name": "SQL query change",
  "delay": 900,
  "active": true,
  "params": {
    "connection": "MY_CONNECTION",
    "sql": "SELECT COUNT(*) FROM my_table",
    "hasLimit": true,
    "limit": 10
  },
  "graceDelaySettings": {"delay": 120, "checkAgainAfterGraceDelay": true}
}
```

### `follow_scenariorun` — Fire when another scenario completes

```json
{
  "id": "trigger_id",
  "type": "follow_scenariorun",
  "name": "Follow scenario",
  "delay": 60,
  "active": true,
  "params": {
    "scenarioId": "UPSTREAM_SCENARIO_ID"
  },
  "graceDelaySettings": {"delay": 0, "checkAgainAfterGraceDelay": false}
}
```

## Reporter (Email) Reference

```json
{
  "id": "reporter_id",
  "name": "send email on failure",
  "active": true,
  "phase": "END",
  "runConditionEnabled": true,
  "runCondition": "outcome != 'SUCCESS'",
  "messaging": {
    "type": "mail-scenario",
    "configuration": {
      "channelId": "my-smtp-channel",
      "subject": "DSS scenario ${scenarioName}: ${outcome}",
      "sender": "noreply@company.com",
      "recipient": "team@company.com",
      "ccRecipient": "",
      "bccRecipient": "",
      "sendAsHTML": false,
      "messageSource": "TEMPLATE_FILE",
      "templateFormat": "FREEMARKER",
      "templateName": "default.ftl",
      "attachments": [
        {
          "type": "DATASET",
          "params": {
            "attachedDataset": "my_output_dataset",
            "isInline": false,
            "exportParams": {
              "selection": {"samplingMethod": "FULL"},
              "format": {"type": "csv", "params": {"style": "excel", "charset": "utf8", "separator": ","}}
            }
          }
        },
        {
          "type": "DASHBOARD_EXPORT",
          "params": {
            "dashboardId": "j4Ju74P",
            "isInline": false,
            "exportFormat": {"paperSize": "A4", "orientation": "LANDSCAPE", "fileType": "PDF", "width": 1754, "height": 1240},
            "shouldUseDashboardFormatSettings": true
          }
        }
      ]
    }
  }
}
```

**`active`**: must be `true` for the reporter to fire — a reporter with `active: false` is silently skipped regardless of other settings.
**`runConditionEnabled`**: when `false`, the `runCondition` expression is ignored and the reporter always fires. Set to `true` to evaluate `runCondition`.
**`runCondition`**: expression evaluated at run end. Common values: `"outcome != 'SUCCESS'"`, `"outcome == 'FAILED'"`, `"true"` (always send).
**`phase`**: `"END"` — reporter fires after the run completes.
**`channelId`**: must match an existing SMTP channel configured in DSS Administration — do not invent it. Ask the user for the channel name before writing a reporter.
**`sender`** / **`recipient`**: required — never leave blank. Ask the user if not provided.
**Variable interpolation** in string fields: `${scenarioName}`, `${outcome}`, `${projectKey}`, and any scenario variables (e.g., `${version_id}`).
