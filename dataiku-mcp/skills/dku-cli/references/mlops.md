# MLOps — model lifecycle, code envs, guardrails, semantic models, macros

Durable shapes and payloads for the LLM Mesh / MLOps surface. Exact CLI flags:
`--help`.

## Model lifecycle (monitor → retrain → deploy → serve)

Visual ML training and saved-model versioning are **UI/`dataikuapi`-only** (no `dku`
verbs). These are the non-obvious `dataikuapi` call shapes.

**Performance-drift check** — compare the active version's training metric against
freshly-scored data, gate on a threshold:
```python
sm = project.get_saved_model("MODEL_ID")
training_auc = sm.get_active_version().get_details().get_performance_metrics()["auc"]
if abs(training_auc - current_auc) > 0.05:   # retrain trigger
    ...
```

**Conditional retrain (scenario)** — retrain, then activate the new version **only if it
clears the bar** (else keep the incumbent):
```python
s.train_model("MODEL_ID")
new = sm.list_versions()[0]; new_auc = new["snippet"].get("auc", 0)
if new_auc >= 0.80:
    sm.set_active_version(new["id"])     # promote only on pass
```
Retrain triggers: scheduled (cron), data-driven (`ds_modified`), performance-driven
(drift check above), or on-demand.

**Import an external MLflow model → saved model** — order matters:
```python
mx = project.get_mlflow_extension()
mx.set_run_inference_info(run_id, "BINARY_CLASSIFICATION", classes, code_env, target_col)
mx.deploy_run_model(run_id, "saved_model_id", evaluation_dataset=dataiku.Dataset("test"))
```

**Call a deployed prediction endpoint** (API node) — path + JSON envelope:
```
POST https://<api-node>/public/api/v1/<service>/<endpoint>/predict
  body: {"features": {...}}   →   resp.json()["result"]["prediction" | "probabilities"]
```
Deploy path: Design → Project Deployer → Automation node; Design → API Deployer → API
node(s). Create the service with `project.create_api_service()` +
`add_prediction_endpoint(endpoint_name, saved_model_id)`.

## Code environments

Isolated Python envs for plugins, recipes, ML, webapps. Three env modes when
pinning an env on a code recipe: `EXPLICIT_ENV` (needs `env_name`), `INHERIT`,
`USE_BUILTIN_MODE`. Only applies to code recipes (`python`/`r`/`pyspark`/
`sparkr`); there is no CLI command to change an existing recipe's env — recreate
or edit in the UI. ML-task envs are UI/`dataikuapi`-only.

**Don't change a code env proactively** — only when a run fails with a clear env
problem (missing package, import error, bad Python version). List envs, filter
by language, ask the user for the exact name, then set `EXPLICIT_ENV`.

### Python version policy (DSS 14)

- 3.6–3.7 removed; 3.8 deprecated; **3.9–3.13 fully supported**; 3.14 limited.
- Use `PYTHON312`/`PYTHON311` for new plugins; include `PYTHON310` unless you
  need 3.11+ features.

### CRITICAL: never `installCorePackages: true` on Python 3.11+

`LEGACY_PANDAS023` installs `pandas==0.23.4` which fails to build; `PANDAS1`
also fails. Set `installCorePackages: false` and pin explicit deps instead:

```json
{"acceptedPythonInterpreters":["PYTHON310","PYTHON311","PYTHON312","PYTHON313"],
 "installCorePackages":false,
 "basePackagesInstallMethod":"PIP_INSTALL",
 "pipPackages":[{"name":"pandas","version":">=2.0,<3"},{"name":"numpy","version":">=1.22,<3"}]}
```

The `dataiku` runtime imports numpy/pandas/dateutil at module load — include
them even if your plugin doesn't use them directly. Other `desc.json` keys:
`forceConda`, `corePackagesSet` (`AUTO`/`LEGACY_PANDAS023`/`PANDAS1`/`PANDAS10`),
`installJupyterSupport`, `condaPackages`, `jarFiles`, `envVars`.

- **Pip name ≠ import name:** pip-install `dataiku-api-client`, `import dataikuapi`.
- MXNet doesn't support NumPy 2 → pin `numpy<2` if using both.
- **Recovery:** a failed `create_code_env()` leaves a broken env — `ce.delete()`
  before retrying. Build log: `$DATA_DIR/code-envs/plugins/<plugin>/build.log`.
- Prefer lazy imports for heavy libs; use `python_version` markers for
  version-specific deps.

## Guardrails

Plugin component that intercepts LLM completions in the Mesh: **block** (raise),
**rewrite** (mutate `input`), or **observe** (trace spans). They chain in order,
stopping at the first exception. Files: `python-guardrails/<name>/guardrail.json`
+ `guardrail.py`.

```python
from dataiku.llm.guardrails import BaseGuardrail

class MyGuardrail(BaseGuardrail):
    def set_config(self, config, plugin_config):
        self.config = config
    def process(self, input, trace):
        with trace.subspan("check") as span:
            msgs = input.get("completionQuery", {}).get("messages", [])
            if msgs and "bad" in msgs[-1].get("content", "").lower():
                raise Exception("Query blocked: prohibited content.")
            resp = input.get("completionResponse", {}).get("text", "")
            # rewrite: input["completionResponse"]["text"] = filtered
            span.attributes["checked"] = True
        return input
```

The `input` dict carries `completionQuery.messages` (present before the call;
last message is the user's current input) and/or `completionResponse.text`
(present after). **Rules:** always `return input` (mutate, don't replace); use
`trace.subspan(name)` and `span.attributes[k]=v` — **never** `trace.set_attribute()`;
raise to block with a user-readable message; read LLM IDs from `config`, never
hardcode; fail **safe** (block on unexpected error). For an LLM-judge pattern,
append the judge's trace: `span.append_trace(resp.trace)`.

## Semantic models (DSS 14.4+)

Map business context onto datasets so the **Semantic Model Query** agent tool
does NL→SQL.

**Critical prerequisite: entities MUST point at SQL-backed datasets** (Snowflake,
Postgres, Redshift, BigQuery, …). Filesystem/UploadedFiles datasets fail at query
time with a polite English refusal ("not accessible via SQL"). If source is on
Filesystem, **sync to a SQL connection first**, then point `datasetRef` at the
SQL dataset. Symptom of getting this wrong looks like a prompt issue but the fix
is the sync.

**Workflow (prefer splice verbs over raw JSON):** `create` (does NOT auto-create
a version) → `create-version v1` → `set-active-version v1` (text-to-SQL reads the
ACTIVE version ONLY — #1 cause of "model not used") → `add-entity --from-dataset
… --pk … --index-values …` → `add-relationship --from … --to … --on|--expression`
→ `add-glossary-term` / `add-metric` / `add-filter` / `add-golden-query` /
`set-manual-values` → `update-index --wait` (re-run after any entity or
`manualValues` change). Verify with the `list-*` commands.

Raw-JSON fallback (`get-version | edit | set-version`) **shallow-merges at the
top level**: passing `{"relationships":[...]}` alone **replaces the whole array**
— always read current state, append, save back.

```json
// version top-level
{"id":"v1","entities":[…],"relationships":[…],"goldenQueries":[…],
 "glossaryTerms":[…],"indexingSettings":{"maxScannedRowsForSQLDatasets":-1}}
// entity (-1 = no row cap; metrics/filters are named pseudo-SQL, not GREL)
{"name":"customer","type":"DATASET","datasetRef":"PROJECT.DATASET",
 "primaryKey":{"attributes":["CustomerID"]},"foreignKeys":[],
 "metrics":[{"name":"Total","pseudoSQLExpression":"COUNT(CustomerID)"}],
 "filters":[{"name":"Sub","pseudoSQLExpression":"Subscribed = 'true'"}],
 "attributes":[{"name":"RiskTolerance","type":"COLUMN","column":"RiskTolerance",
   "dssType":"string","distinctValuesHandlingMode":"MANUAL",
   "manualValues":["Low","Medium","High"],"indexDistinctValues":true,
   "resolveInUserRequests":true}]}
// relationship — THREE fields. left = firstEntity, right = secondEntity.
{"firstEntity":"customer","secondEntity":"order",
 "pseudoSQLExpression":"left.CustomerID = right.CustomerID"}
// golden query — NL→SQL few-shot, biggest quality driver
{"name":"…","question":"…","generatedSql":"SELECT …"}
```

- **Don't guess relationship field names** — it's `firstEntity`/`secondEntity`
  (NOT `leftEntity`/`fromEntity`); export a UI-built example to confirm shapes.
- `datasetRef` must be fully qualified `PROJECT.DATASET`. Entity needs a
  `primaryKey` for cardinality inference. No `id`/cardinality on relationships.
- `manualValues` + `update-index` drives value resolution ("high risk" →
  `RiskTolerance='High'`); stale index → agent returns no rows.
- Unknown shapes (export from UI to confirm): `foreignKeys[]`, `glossaryBindings[]`,
  `sqlGenerationConfig`, `attribute.type` beyond `COLUMN`, `entity.type` beyond
  `DATASET`.

## Macros (runnables)

On-demand plugin utilities. Files: `python-runnables/<name>/runnable.json` +
`runnable.py`.

`runnable.json`: `meta{label,description,icon}`, `impersonate`, `resultType`,
`resultLabel`, `macroRoles[]`, `params[]`.

| `resultType` | Python return |
|---|---|
| `HTML` | `str` (HTML) |
| `RESULT_TABLE` | `ResultTable` / JSON table |
| `FILE` | `bytes` |
| `URL` | `str` (redirect) |
| `NONE` | `None` |

`macroRoles[].type` controls where it appears: `DATASET`, `DATASETS`,
`MANAGED_FOLDER`, `SAVED_MODEL`, `API_SERVICE`, `API_SERVICE_VERSION`,
`PROJECT_MACROS`, `PROJECT_CREATOR`. A role's `targetParamsKey` binds the
selected object(s) to a param. Params support `SELECT` (`selectChoices`),
`BOOLEAN`, `INT`, `STRING`, `STRINGS`, `DATASET(S)`, and
`visibilityCondition: "model.<param> == …"`.

```python
from dataiku.runnables import Runnable, ResultTable

class MyMacro(Runnable):
    def __init__(self, project_key, config, plugin_config):
        self.config = config
        self.project = dataiku.api_client().get_project(project_key)
    def get_progress_target(self):
        return (count, "FILES")   # unit: NONE|SIZE|FILES|RECORDS|<str>; None = indeterminate
    def run(self, progress_callback):
        # ... progress_callback(i+1) ...
        table = ResultTable()           # for RESULT_TABLE
        table.add_column("name", "Name", "STRING")
        table.add_record(["Item 1"])
        return table                    # or HTML str / bytes / URL str
```

Run from a scenario via a "Run DSS plugin" step, or programmatically:
`project.get_runnable("plugin_macro").run(params={...})`. Troubleshooting:
macro absent → check `macroRoles` type + reload plugin; progress stuck →
`get_progress_target()` values; timeout → use progress callbacks for long ops.

### Custom metric/check probes

When built-in DQ rules can't express the gate. **Prefer built-in DQ rules first.**

- **Custom metric** — Python probe returns a `MetricReport`:
  `from dataiku.custommetrics import *; r=MetricReport(); r.add_metric("null_ratio", x); return r`.
- **Custom check** — returns a verdict:
  `from dataiku.customcheck import *; def check(dataset, config): return CheckResult(CheckResult.ERROR|WARNING|OK, msg)`.
  `ERROR` fails the build/scenario; `WARNING` is soft.
- Plugin form: `python-probes/<n>/probe.{json,py}`, `python-checks/<n>/check.{json,py}`.

## Manifest section style (App Designer / Project Setup)

Section fields: `sectionTitle` (plain text header — **do NOT** bake the title
into the body as `<h3>`), `sectionText` (body), `tiles[]`, optional
`visibilityCondition`. Body is **markdown**; the only safe HTML escape hatches
are `<i class="icon-warning-sign|icon-info-sign|icon-ok-sign">`, `<br>`, `<b>`.
Custom `<div>`/inline styles/color spans are brittle and break on theme change /
clone — split sections or move rich content to a wiki article instead.

Cross-refs use wiki link syntax, exact IDs (case- and separator-sensitive —
`Build_All` ≠ `BUILDALL`): `[label](article:ID)`, `(scenario:ID)`,
`(dataset:NAME)`, `(dashboard:ID)`, `(folder:ID)`, `(recipe:NAME)`. Get the
exact id from `dku <noun> list -o json`; don't guess by uppercasing.

`visibilityCondition` (CEL-like: `model.<name>`, `&&`, `==`) gates a param or a
whole section against `model.<paramName>`. Always pair a toggle param with a
`defaultValue` so new instances render deterministically. Tile prompts: plain
imperative voice, no trailing punctuation (`Upload data`, not `Click to upload!`).
