# Reference: MLOps

Durable shapes and payloads for the LLM Mesh / MLOps surface. Exact CLI flags:
`--help`.

## Model lifecycle (monitor → retrain → deploy → serve)

Training, configuration, and thresholds have `dku ml` / `dku model` verbs (see
`playbooks/analytics-apps.md`). The flows below are the non-obvious `dataikuapi`
call shapes for what the CLI does not cover (drift gates, MLflow import, API node).

### ML-task settings payload shapes (when editing raw settings)

`dku ml set-params / set-split / set-feature` handle these correctly; if you must
edit raw settings via `dataikuapi`, the shapes (verified DSS 14.6):

- **Prediction hyperparameters are grid dicts** `{"values": [...], "limit": {...},
  "range": {...}, "gridMode": ...}`. Replace ONLY `values` — see
  `../playbooks/analytics-apps.md` for the failure mode if you rebuild the dict.
- **Clustering hyperparameters are plain JSON arrays** (`kmeans_clustering.k:
  [3, 4]`) — a different shape from prediction; writing a string or grid dict
  fails the save with `Expected BEGIN_ARRAY`.
- **`per_feature[col].rescaling` is a string enum** (`"NONE" | "AVGSTD" |
  "MINMAX"`), not an object — `{"method": "NONE"}` fails the save.
- **`splitParams.ssdTrainingRatio`** is the train fraction (default 0.8);
  clustering tasks have no `splitParams` at all.
- **`userMeta.activeClassifierThreshold`** on the version details is the live
  binary-classification cut-off; DSS sets it automatically at deploy — CLI-facing
  detail and fix in `../playbooks/analytics-apps.md`.

**Performance-drift check** — compare the active version's training metric against
freshly-scored data, gate on a threshold:
```python
sm = project.get_saved_model("MODEL_ID")
ver = sm.get_active_version()                # dict, not an object
details = sm.get_version_details(ver["id"])
training_auc = details.get_performance_metrics()["auc"]
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

CLI workflow (create/set/update a plugin code env) and its gotchas:
`../playbooks/extensions-admin.md`.

### Python version policy

- 3.6–3.7 removed; 3.8 deprecated; **3.9–3.13 fully supported**; 3.14 limited.
- Use `PYTHON312`/`PYTHON311` for new plugins; include `PYTHON310` unless you
  need 3.11+ features.

### Never `installCorePackages: true` on Python 3.11+

`LEGACY_PANDAS023` installs `pandas==0.23.4` which fails to build; `PANDAS1`
also fails. Set `installCorePackages: false` and pin explicit deps instead:

```json
{"acceptedPythonInterpreters":["PYTHON310","PYTHON311","PYTHON312","PYTHON313"],
 "installCorePackages":false,
 "basePackagesInstallMethod":"PIP_INSTALL",
 "pipPackages":[{"name":"pandas","version":">=2.0,<3"},{"name":"numpy","version":">=1.22,<3"}]}
```

Other `desc.json` keys: `forceConda`, `corePackagesSet`
(`AUTO`/`LEGACY_PANDAS023`/`PANDAS1`/`PANDAS10`), `installJupyterSupport`,
`condaPackages`, `jarFiles`, `envVars`.

- **Pip name ≠ import name:** pip-install `dataiku-api-client`, `import dataikuapi`.
- MXNet doesn't support NumPy 2 → pin `numpy<2` if using both.
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

## Semantic models

Semantic model payload shapes and workflow → `semantic-models.md` and
`../playbooks/semantic-layer.md`.

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
`project.get_macro("plugin_macro").run(params={...})`. Troubleshooting:
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

App Designer manifest section fields → `references/app-designer.md`.
