# Reference: Plugin & Recipe Parameter Types

Durable shapes for plugin/recipe/webapp parameter definitions (the `params:[…]` blocks in
`recipe.json` / `connector.json` / `webapp.json`). Dataset definitions, schema, and
partitioning live in `datasets-and-types.md`.

Every parameter shares: `{name, label, type, mandatory?, description?, defaultValue?, visibilityCondition?}`.
`name` is the stable config key; read in Python via `get_recipe_config()` / `get_plugin_config()` /
`get_webapp_config()`. Below: `type` → JSON-extra fields → Python deserialization.

### Core types

| `type` | Extra fields | Python |
|---|---|---|
| `STRING` / `TEXTAREA` / `PASSWORD` | `regexpFilter` (STRING) | `str` |
| `INT` | `minI`, `maxI` | `int` |
| `DOUBLE` | `minD`, `maxD` | `float` |
| `BOOLEAN` | — | `bool` |
| `DATE` | — | `str` (Zulu) |
| `STRINGS` / `INTS` / `DOUBLES` | `allowDuplicates` (STRINGS) | `list` |
| `SELECT` | `selectChoices:[{value,label}]` OR `getChoicesFromPython:true` | `str` |
| `MULTISELECT` | `selectChoices` | `list[str]` |

### Complex / object types

| `type` | Extra fields | Python |
|---|---|---|
| `MAP` | — | `dict` (unordered) |
| `KEY_VALUE_LIST` | — | `list[dict]` (`[{from,to}]`, ordered) |
| `OBJECT_LIST` | `subParams:[…]` (param defs) | `list[dict]` |
| `DATASET` / `DATASETS` | `canSelectForeign` | `str` / `list[str]` |
| `COLUMN` / `COLUMNS` | `columnRole` (input role), `allowedColumnTypes:[…]` | `str` / `list[str]` |
| `DATASET_COLUMN` / `DATASET_COLUMNS` | `datasetParamName` (a DATASET param) | `str` / `list[str]` |
| `MANAGED_FOLDER` | `canSelectForeign` | `str` |
| `SAVED_MODEL` | — | `str` |

### Special / DSS-object / AI types

| `type` | Extra fields | Notes |
|---|---|---|
| `LLM` | `llmUsagePurpose: GENERIC_COMPLETION\|TEXT_EMBEDDING_EXTRACTION\|IMAGE_EMBEDDING_EXTRACTION\|IMAGE_GENERATION\|IMAGE_INPUT` | → LLM ID |
| `KNOWLEDGE_BANK` | — | RAG; → KB name |
| `CODE_ENV` / `CONNECTIONS` / `PROJECT` / `SCENARIO` | — | → ID/name |
| `CONNECTION` | `allowedConnectionTypes` | → connection name |
| `CLUSTER` | `clusterPermissions` | → cluster ID |
| `API_SERVICE_VERSION` | `apiServiceParamName` (an API_SERVICE param) | → service-version ID |
| `ML_TASK` | `visualAnalysisParamName` (a VISUAL_ANALYSIS param) | → ML-task ID |
| `SEPARATOR` | `description` (HTML) | display-only divider |
| `PRESET` | `parameterSetId` | values from a Parameter Set |
| `CREDENTIAL_REQUEST` | `credentialRequestSettings.{type: SINGLE_FIELD\|BASIC\|OAUTH2, authorizationEndpoint, tokenEndpoint, scope}` | per-user secret/OAuth |

### Dynamic params & visibility

- Dynamic SELECT: set `getChoicesFromPython:true` + component-level `paramsPythonSetup:"file.py"`. The
  `resource/<file>.py` (NOT `_resource/`) defines `do(payload, config, plugin_config, inputs)` returning
  `{"choices":[{value,label}]}`. `payload.parameterName` selects which param to populate.
- Cascading: child SELECT adds `triggerParameters:["parent_param"]` (reloads when parent changes);
  `disableAutoReload:true` reloads only on trigger, not on form open.
- `visibilityCondition` is a JS expression over `model.<param>`: e.g.
  `"model.use_custom == true && model.mode == 'advanced'"`, `"model.features.indexOf('x') >= 0"`.
