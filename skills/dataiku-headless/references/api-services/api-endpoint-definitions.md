---
name: api-endpoint-definitions
description: Configure API Service endpoints for saved models, Python/R functions, custom predictors, dataset lookups and SQL queries.
---

# API Endpoint Definitions

Use this reference when adding or changing an endpoint. Read
[API Services](../api-services.md) for the create/update, deletion and publication
workflows.

- [Shared fields](#shared-fields)
- [Visual models](#visual-models)
- [Python and R functions](#python-and-r-functions)
- [Python and R custom prediction](#python-and-r-custom-prediction)
- [Dataset lookup](#dataset-lookup)
- [SQL query](#sql-query)
- [Code environments](#code-environments)
- [Managed-folder resources](#managed-folder-resources)
- [Lookups and prediction enrichment](#lookups-and-prediction-enrichment)
- [Test queries](#test-queries)
- [Validation](#validation)

Pass each endpoint definition in `update_api_service(endpoints=[...])`. Put example
request bodies inside that definition's `testQueries[].q`; a request body is the
input to an endpoint, such as `{"features": {"age": 35}}`.

For an existing endpoint, start from `get_api_service` and preserve fields outside
the requested change: matching IDs replace the complete definition. Never submit
redaction placeholders. Use `remove_endpoint_ids` for
[endpoint deletion](../api-services.md#workflow-for-deleting-endpoints).

Examples below are minimal and synthetic. Replace angle-bracket placeholders with
IDs, names and columns discovered in the target project. Apply optional settings
only when the endpoint needs them.

## Shared fields

An endpoint definition is one object inside the tool's `endpoints` list. Paths
below are relative to that object; `[]` denotes a list entry. For example,
`individualExplanationParams.method` means
`{"individualExplanationParams": {"method": "SHAPLEY"}}`.
There is no `params` or `payload` wrapper. Except for the explicitly labeled
visual-model tool call, explanation fragment and [test queries](#test-queries),
JSON examples show one complete endpoint object to put in `endpoints`.

| Path within endpoint | What to supply |
| --- | --- |
| `id` | Required endpoint ID, unique within the service. Use the existing ID when replacing an endpoint. |
| `type` | Required endpoint type from the family sections below. |
| `tags` | Optional list of strings. Preserve existing tags when editing. |
| `openAPI.enabled`, `openAPI.isManual` | Optional documentation booleans inside `openAPI`. Preserve existing documentation unless changing it is requested. |
| `openAPI.title`, `openAPI.content`, `openAPI.description` | Strings inside `openAPI`; `description` is optional. `content` contains the OpenAPI document text. |
| `testQueries` | Optional saved request examples; see [Test queries](#test-queries). Saving them does not execute them. |

## Visual models

Supply `modelRef`: the saved-model ID deployed to the Flow. Use `list_saved_models`,
`list_saved_model_versions` and `get_saved_model_version_details` to inspect its
model type, active version, algorithm and reported input features. These tools
return model summaries; if preprocessing or engine compatibility is not included,
check it in the Dataiku model UI before selecting the scoring engine. Use the model
reference returned by inspection, including project qualification when present.
Packaging captures the active version; later model changes require a new package.

| Endpoint `type` | Model to serve |
| --- | --- |
| `STD_PREDICTION` | Classification or regression, including imported MLflow saved models. |
| `STD_CLUSTERING` | Clustering. |
| `STD_FORECAST` | Time series forecasting. Test requests need history, time/series columns and any required future external features. |
| `STD_CAUSAL_PREDICTION` | Causal prediction. |
| `STD_MULTITARGET_PREDICTION` | Multitarget prediction; requires a Dataiku version supporting this endpoint type. |

### Choose the scoring engine

`useJava=true` selects Local (Optimized); `false` selects Local (Python).
For classification/regression, including multitarget regression:

1. Find the training engine and algorithm in Dataiku's
   [scoring compatibility matrix](https://doc.dataiku.com/dss/latest/machine-learning/scoring-engines.html#algorithms).
   A **Yes** under **Local (Optimized)** permits `useJava=true` when the model's
   preprocessing is also supported by that engine. Prefer it for faster scoring
   when explanations are not needed.
2. If optimized scoring is unavailable, use `false` only when **Local (Python)**
   is **Yes**. If neither local engine is supported, the model cannot be served
   on an API node. Spark/SQL support alone is insufficient.
3. For explanations, select `false` and a model supporting Python API-node
   scoring and explanations. Multitarget regression follows its underlying
   algorithm; do not force `false` merely because it is multitarget.

Use `false` for `STD_CLUSTERING`, `STD_FORECAST`, `STD_CAUSAL_PREDICTION` and
imported MLflow models. When model details expose `javaScoreCompatibility` or
`pythonApiNodeScoreCompatibility`, honor their `compatible` flag and `reason`:
model-specific restrictions take precedence over the algorithm-level matrix.

### Definition shape and options

Undotted paths below are fields directly in the endpoint object, alongside `id`
and `type`. Dotted paths identify fields inside `individualExplanationParams`.

| Path within endpoint | Required / type | Value or rule |
| --- | --- | --- |
| `modelRef` | Required string | Discovered saved-model reference. |
| `useJava` | Set explicitly; boolean | Choose using the rules above. |
| `computePropensity` | Optional boolean; causal only | Set `true` only when a propensity model was trained; otherwise `false`. |
| `outputExplanations` | Optional boolean; default `false` | Enable only for a model supporting explanations, with `useJava=false`. |
| `individualExplanationParams.method` | String, when enabling explanations | `ICE` or `SHAPLEY`. |
| `individualExplanationParams.nbExplanations` | Integer, when enabling explanations | Number of features to explain. |
| `individualExplanationParams.drawInScoredSet` | Optional tuning field | Preserve the existing value unless changing explanation sampling. |
| `individualExplanationParams.subChunkSize` | Optional tuning field | Preserve the existing value unless tuning explanation computation. |
| `individualExplanationParams.shapleyBackgroundSize` | Optional tuning field | Preserve the existing value unless changing the SHAP background sample size. |
| `mlFlowOutputStyle` | String; imported MLflow only | `PARSED` restructures output into Dataiku predictions; `RAW` preserves model output. Match the model's output schema and required response. |
| `enrichMapping` | Optional list of objects | Dataset feature lookups; see [Enrichment](#lookups-and-prediction-enrichment). |

Example `update_api_service` arguments for an optimized-compatible prediction
model, without explanations:

```json
{
  "project_key": "<project key>",
  "service_id": "<service ID>",
  "endpoints": [{
    "id": "<endpoint ID>",
    "type": "STD_PREDICTION",
    "modelRef": "<saved-model ID>",
    "useJava": true,
    "outputExplanations": false
  }]
}
```

To enable explanations on a supported model, set these fields in that same
endpoint object (retain `id`, `type`, `modelRef` and other existing fields):

```json
{
  "useJava": false,
  "outputExplanations": true,
  "individualExplanationParams": {
    "method": "SHAPLEY",
    "nbExplanations": 3
  }
}
```

This second block is a fragment, not a complete replacement endpoint.

[Visual model guidance](https://doc.dataiku.com/dss/latest/apinode/endpoint-std.html),
[MLflow output options](https://doc.dataiku.com/dss/latest/apinode/endpoint-mlflow.html).

## Python and R functions

Use `PY_FUNCTION` or `R_FUNCTION` for application logic returning a JSON-serializable
result. Supply `code` and `userFunctionName`; the named function must exist in the
code. Request field names become function argument names.

Optional settings are [code environments](#code-environments) (`envSelection`) and
[folder resources](#managed-folder-resources) (`inputFolderRefs`). R also accepts
`passArgumentsAsList`: false passes named arguments; true passes one list containing
all parameters, so write the function to accept that list.

Python example:

```json
{
  "id": "<endpoint ID>",
  "type": "PY_FUNCTION",
  "userFunctionName": "run",
  "code": "def run(value):\n    return {'value': value}\n",
  "envSelection": {"envMode": "INHERIT"},
  "testQueries": [{"name": "example", "q": {"value": 1}}]
}
```

For R, use `type="R_FUNCTION"`, `userFunctionName="run"`,
`code="run <- function(value) { list(value = value) }"`, and
`passArgumentsAsList=false`. Select an R environment if choosing an explicit one.

Function endpoints do not support `enrichMapping`. They can perform writes when
invoked; inspect that behavior before running a test.

[Python function guidance](https://doc.dataiku.com/dss/latest/apinode/endpoint-python-function.html),
[R function guidance](https://doc.dataiku.com/dss/latest/apinode/endpoint-r-function.html).

## Python and R custom prediction

Use `CUSTOM_PREDICTION` or `CUSTOM_R_PREDICTION` for user-written prediction logic.
Supply `code` and `modelType` (`REGRESSION` or `CLASSIFICATION`). Both types accept
`envSelection`, optional `inputFolderRef` for model artifacts, and `enrichMapping`
for feature lookups. R also requires `userFunctionName`.

### Python contract

Define a class extending `RegressionPredictor` or `ClassificationPredictor` from
`dataiku.apinode.predict.predictor`, matching `modelType`. Dataiku discovers the
class; no `userFunctionName` is needed. Its constructor accepts `data_folder=None`,
the packaged folder's local path when a folder is supplied.

Implement `predict(self, features_df)` for a pandas DataFrame of multiple rows:

| Model type | Accepted return values |
| --- | --- |
| Regression | Prediction Series, or `(prediction_series, custom_keys_list)`. |
| Classification | Prediction Series, `(prediction_series, probabilities_df)`, or `(prediction_series, probabilities_df, custom_keys_list)`. Probability columns identify classes. |

Return one prediction per input row. Probability rows and any per-row custom-keys
list must align with the input rows.

Minimal regression example using the input's numeric `value` feature:

```json
{
  "id": "<endpoint ID>",
  "type": "CUSTOM_PREDICTION",
  "modelType": "REGRESSION",
  "envSelection": {"envMode": "EXPLICIT_ENV", "envName": "<Python environment name>"},
  "code": "from dataiku.apinode.predict.predictor import RegressionPredictor\n\nclass Predictor(RegressionPredictor):\n    def __init__(self, data_folder=None):\n        self.data_folder = data_folder\n\n    def predict(self, features_df):\n        return features_df['value'].astype(float)\n"
}
```

Select an environment with the required packages. If the actual model uses
serialized artifacts, supply `inputFolderRef` and load them from `data_folder`.

[Python predictor guidance](https://doc.dataiku.com/dss/latest/apinode/endpoint-python-prediction.html).

### R contract

Set `userFunctionName` to a function defined in `code`. Features become named
arguments unless `passArgumentsAsList=true`, which passes one list.

| Model type | Accepted return values |
| --- | --- |
| Regression | Numeric prediction, or a list with `prediction` and optional `customKeys`. |
| Classification | Class label, or a list with `prediction`, optional `probas` (class-to-probability mapping), and optional `customKeys`. |

```json
{
  "id": "<endpoint ID>",
  "type": "CUSTOM_R_PREDICTION",
  "modelType": "REGRESSION",
  "userFunctionName": "predict_value",
  "passArgumentsAsList": false,
  "code": "predict_value <- function(value) { as.numeric(value) }",
  "envSelection": {"envMode": "INHERIT"}
}
```

[R predictor guidance](https://doc.dataiku.com/dss/latest/apinode/endpoint-r-prediction.html).

## Dataset lookup

Use `DATASETS_LOOKUP` with a non-empty `lookups` list. For each lookup, supply a
dataset reference, deployment policy, key mappings and returned columns. Inspect
the dataset schema before choosing columns. A lookup returns at most one matched
dataset row for each input record; choose how to handle multiple matches.

```json
{
  "id": "<endpoint ID>",
  "type": "DATASETS_LOOKUP",
  "lookups": [{
    "datasetRef": "<dataset name>",
    "packagingType": "REFERENCED",
    "on": [{
      "inputLookupKey": "<request field>",
      "resourceLookupCol": "<dataset key column>"
    }],
    "columnsMapping": {"<dataset value column>": "<response field>"},
    "missingLookupKeyBehavior": "ERROR",
    "notFoundBehavior": "IGNORE",
    "multiMatchBehavior": "ERROR"
  }]
}
```

This example requires a SQL dataset and a working serving-side connection mapping.
Choose the [data deployment policy](#choose-bundled-or-referenced-data) for the
actual use case; `REFERENCED` is not a default for every lookup.

## SQL query

Use `SQL_QUERY` with a discovered SQL `connection` name and a non-empty `queries`
list. Query fields are nested inside `queries[]`:

| Path within endpoint | What to supply |
| --- | --- |
| `queries[].query` | SQL text. Use unquoted `?` placeholders for values. |
| `queries[].inputParameters[].name` | Parameter name string, one ordered entry per placeholder. Set `inputParameters: []` when there are no parameters. |
| `queries[].maxResults` | Optional row limit; `-1` means unlimited. Use a finite limit for bounded tests. |
| `queries[].postCommit` | Optional boolean, default false. Enable when the intended write requires a commit. |

```json
{
  "id": "<endpoint ID>",
  "type": "SQL_QUERY",
  "connection": "<SQL connection name>",
  "queries": [{
    "query": "SELECT <value column> FROM <table> WHERE <key column> = ?",
    "inputParameters": [{"name": "lookup_id"}],
    "maxResults": 100,
    "postCommit": false
  }]
}
```

Use actual table/column names; parameters bind values, not SQL identifiers. Query
entries execute in order on the same connection. Within a multi-statement entry,
only the last SELECT receives the parameters, or the last statement if there is no
SELECT. Use separate entries when different statements need parameter binding.

Inspect non-SELECT statements for side effects before testing. Confirm the serving
infrastructure has the connection mapping and required drivers; saving its name
does not provision a connection.

[SQL query guidance](https://doc.dataiku.com/dss/latest/apinode/endpoint-sql-query.html).

## Code environments

Function and custom prediction endpoints use the top-level `envSelection` object.
Each value below is the object assigned to `envSelection` (not the whole endpoint):

| Choice | Object |
| --- | --- |
| Inherit the configured default | `{"envMode": "INHERIT"}` |
| Use the built-in environment | `{"envMode": "USE_BUILTIN_MODE"}` |
| Select an environment | `{"envMode": "EXPLICIT_ENV", "envName": "<discovered environment name>"}` |

Keep inheritance when no environment change is needed. Discover environments with
`list_code_envs(language="PYTHON")` or `list_code_envs(language="R")`. Inspect the
selected name with `search_mode="exact"` and `include_details=true` before choosing
it. Verify required packages and serving/build compatibility, then copy the exact
name into `envName`. Omit `envName` for inherited or built-in modes. Use `envMode`,
not the `mode` key used in project settings.

When an endpoint uses a dedicated code environment, packaging includes its
definition. Dataiku automatically installs that environment when loading the
service on the API node; no separate environment-transfer step is needed. The
serving infrastructure must support the required runtime and be able to install
its dependencies.

Prefer a dedicated code environment when external packages are needed. Packages
manually added to Design's built-in environment are not included this way; an
administrator must install them in the API node's built-in environment separately.
See [Dataiku's environment packaging guidance](https://doc.dataiku.com/dss/latest/apinode/endpoint-python-function.html)
and [Code environments](../administration/code-environments.md) for discovery
parameters and permissions.

## Managed-folder resources

| Endpoint family | Definition field | How code accesses packaged files |
| --- | --- | --- |
| Python/R functions | `inputFolderRefs: [{"ref": "<managed-folder ID>"}]` | Python: `folders` global list of local paths. R: `dkuAPINodeGetResourceFolders()`. Paths follow reference order. |
| Python/R custom prediction | `inputFolderRef: "<managed-folder ID>"` | Python: constructor's `data_folder`. R: `dkuAPINodeGetResourceFolders()`. |

Discover folder IDs and inspect required filenames with the
[managed-folder tools](../managed_folders.md). Packaging snapshots the contents.
Read those packaged local paths in endpoint code; do not assume a live Design
session or use Design dataset APIs to fetch runtime data.

## Lookups and prediction enrichment

### When to use each

| Need | Recommended configuration |
| --- | --- |
| Return stored attributes for a key, without running a model | `DATASETS_LOOKUP` with `lookups`. For example, accept a customer email and return selected customer attributes. |
| Score a record when the caller knows its identifiers and current transaction details, but lacks some model features | Add `enrichMapping` to the prediction endpoint. The API node retrieves the missing features before scoring; the caller gets a prediction in one request. |
| Score a record when the caller already supplies all required features | Keep the prediction endpoint without enrichment unless a specific feature must come from a managed lookup source. |

For example, a fraud request can supply `customer_id` and the transaction amount;
enrichment retrieves the customer's historical order count. Map the dataset column
to the exact feature name expected by the model in `columnsMapping`. Prepare
historical aggregates upstream; enrichment retrieves stored values at request time.

Choose keys (including composite keys when needed) that identify one dataset row.
Multiple lookup entries can retrieve attributes from different datasets. Retrieve
only the fields needed by the caller or model, and choose a
[data deployment policy](#choose-bundled-or-referenced-data) that meets freshness
requirements.

For required model features, prefer `ERROR` on missing keys or unmatched records
unless the model's missing-value handling or the intended record-skipping behavior
justifies `IGNORE` or `DROP_ROW`. Test a valid match, missing key, unknown key and
duplicate match. For enrichment, include a test that omits the features being
retrieved; verify both the retrieved values and the prediction.

[Dataset lookup guidance](https://doc.dataiku.com/dss/latest/apinode/endpoint-dataset-lookup.html),
[prediction enrichment guidance](https://doc.dataiku.com/dss/latest/apinode/enrich-prediction-queries.html),
[Knowledge Base use case](https://knowledge.dataiku.com/latest/deploy/api-deployment/concept-query-enrichments.html).

### Configure the mappings

Use `lookups` on `DATASETS_LOOKUP`, or `enrichMapping` on visual/custom prediction
endpoints. The table uses `lookups[]` paths; for prediction enrichment, substitute
`enrichMapping[]` for `lookups[]`. Each entry has the same structure:

| Path within endpoint | What to supply |
| --- | --- |
| `lookups[].datasetRef` | Discovered dataset name/reference. |
| `lookups[].packagingType` | `BUNDLED_TOCONNECTION` or `REFERENCED`; choose using the table below. |
| `lookups[].on` | Non-empty list of `{"inputLookupKey": "<request field>", "resourceLookupCol": "<dataset key column>"}` pairs. |
| `lookups[].columnsMapping` | Dataset column → returned/enriched field name, for each column to retrieve. |
| `lookups[].missingLookupKeyBehavior` | Missing request key: `ERROR` fails the lookup, `IGNORE` continues without enrichment, `DROP_ROW` skips the record. |
| `lookups[].notFoundBehavior` | No matching row: `ERROR`, `IGNORE`, or `DROP_ROW`, with the same meanings. |
| `lookups[].multiMatchBehavior` | Multiple matches: `ERROR`, `DROP_ROW`, or `KEEP_FIRST`. The first row has no guaranteed business ordering. |

Inspect dataset schemas with the [dataset tools](../datasets.md). Preserve prediction
`returnPostEnrichData` and `auditPostEnrichData`; enable them only when returning or
logging enriched fields is intended. Functions do not support this enrichment.

### Choose bundled or referenced data

| Policy | `lookups[].packagingType` | Use when | Prerequisites and refresh |
| --- | --- | --- | --- |
| Bundled | `BUNDLED_TOCONNECTION` | A relatively small lookup table should be released as a snapshot with the service. Dataiku generally recommends this for tables up to a few million rows; also consider row size and package/import cost. Sources can be SQL or other supported datasets. | Requires private bundled-data SQL storage on serving infrastructure. Refresh through a new package and deployment. |
| Referenced (SQL only) | `REFERENCED` | An existing production SQL table should update independently of service releases, or packaging its contents is undesirable. | Requires a serving-side connection mapping to the table. Freshness follows table updates; serving depends on that database's availability and latency. |

Bundled data is copied into the package, then loaded into private SQL storage on
deployment. For Design UI tests, an administrator configures that storage under
Administration > Settings > Deployer > API Designer: Testing. A missing connection
is a setup prerequisite, not a reason to reject bundled data for every use case.
The Bundled UI policy uses `BUNDLED_TOCONNECTION`; `BUNDLED_INTERNAL` is not a synonym.

For referenced data, verify the production table/schema and connection mapping.
Design connectivity alone does not establish serving-side access. These tools do
not provision storage or remap connections.

[Deployment-mode guidance](https://doc.dataiku.com/dss/latest/apinode/enrich-prediction-queries.html#deployment-options),
[Knowledge Base comparison](https://knowledge.dataiku.com/latest/deploy/api-deployment/concept-query-enrichments.html).

## Test queries

Save examples as `testQueries: [{"name": "<label>", "q": {...}}]` in the endpoint
definition. Each block below is **one entry in `testQueries`**, not an endpoint
definition. Its `q` is the request body. Replace synthetic feature names and values
with those required by the inspected model; use representative records from a
suitable dataset when available.

### Classification and regression

`STD_PREDICTION` uses `features` for binary/multiclass classification and regression.
Custom prediction uses the same wrapper; its feature contract comes from the code.

```json
{
  "name": "representative-customer",
  "q": {"features": {"age": 35, "annual_income": 65000, "region": "north"}}
}
```

Check the predicted class and probabilities for classification, or a numeric
prediction for regression. Input features must match the model; omit the target.

### Clustering

`STD_CLUSTERING` also uses `features`, with the columns used by the clustering model:

```json
{
  "name": "customer-segment",
  "q": {"features": {"orders_last_year": 12, "average_order_value": 75.5}}
}
```

Check cluster assignment and any anomaly/distance outputs the model provides.

### Multitarget prediction

`STD_MULTITARGET_PREDICTION` takes one feature record, not one request per target:

```json
{
  "name": "multitarget-record",
  "q": {"features": {"temperature": 18.5, "wind_speed": 7.2}}
}
```

Omit all target values. Check that predictions cover the model's expected targets.

### Causal prediction

For `STD_CAUSAL_PREDICTION`, send covariates in `features`; omit both the outcome
and treatment variables:

```json
{
  "name": "treatment-effect",
  "q": {"features": {"age": 35, "prior_purchases": 4}}
}
```

Check the treatment-effect output and, when enabled, propensity output.

### Forecasting: one series

`STD_FORECAST` uses `items`, containing historical timestamps and target values:

```json
{
  "name": "single-series-history",
  "q": {"items": [
    {"date": "2025-01-01T00:00:00.000", "sales": 10},
    {"date": "2025-01-02T00:00:00.000", "sales": 12},
    {"date": "2025-01-03T00:00:00.000", "sales": 11}
  ]}
}
```

The forecast starts after the last historical timestamp and spans the trained
horizon. Supply enough history for the model's window/seasonality requirements;
these short examples illustrate shape, not sufficient history for every model.

### Forecasting: multiple series

Include the model's series identifier column(s) on every item:

```json
{
  "name": "two-series-history",
  "q": {"items": [
    {"store_id": "A", "date": "2025-01-01T00:00:00.000", "sales": 10},
    {"store_id": "A", "date": "2025-01-02T00:00:00.000", "sales": 12},
    {"store_id": "B", "date": "2025-01-01T00:00:00.000", "sales": 20},
    {"store_id": "B", "date": "2025-01-02T00:00:00.000", "sales": 18}
  ]}
}
```

Check that each requested series has its expected forecast.

### Forecasting: external features

Include external features in history and their known future values for at least
one full forecast horizon. Omit the target on future rows. This example assumes a
two-day horizon and daily frequency:

```json
{
  "name": "history-and-future-promotions",
  "q": {"items": [
    {"date": "2025-01-01T00:00:00.000", "sales": 10, "promotion": 0},
    {"date": "2025-01-02T00:00:00.000", "sales": 12, "promotion": 1},
    {"date": "2025-01-03T00:00:00.000", "sales": 11, "promotion": 0},
    {"date": "2025-01-04T00:00:00.000", "promotion": 1},
    {"date": "2025-01-05T00:00:00.000", "promotion": 0}
  ]}
}
```

For multiple series, include identifiers on historical and future rows. Match the
model's time column, frequency, target, identifiers and external-feature types.

[Dataiku model test-query examples](https://doc.dataiku.com/dss/latest/apinode/endpoint-std.html#testing-your-endpoint).

### Other endpoint families

| Endpoint family | Example `q` |
| --- | --- |
| Python/R function | `{"value": 1}` for the function examples above. |
| Dataset lookup | `{"data": {"<request field>": "<value>"}}` |
| SQL query | `{"lookup_id": "<value>"}` for the SQL example above. |

### Headers and health checks

Optional `headers: [{"key": "X-Example", "value": "example"}]` belongs alongside
`name` and `q`, when supported by the Dataiku version. Preserve existing headers;
never copy redacted credentials. Prediction `healthCheckQueries` are separate from
named test queries; preserve their existing structure when editing.

## Validation

Before saving, check the selected family's required fields and referenced objects:
active model version and input features; function/class and return shape; environment
packages and folder files; SQL connection/parameter order; or lookup columns and
data policy.

Re-read the service after saving. Dataiku may detect remaining configuration errors
only when packaging or loading the endpoint. Saving queries or publishing a
package does not run tests. To test execution through these tools, deploy a
packaged version and follow
[API Deployer testing](../api-deployer.md#test-deployed-endpoints). For Design
pre-publication execution, use the Dataiku UI. Report success only after checking
that the executed queries have no request/record errors and their outputs match
the expected behavior.
