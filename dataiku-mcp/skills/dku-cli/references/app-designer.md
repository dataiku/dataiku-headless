# Reference: App Designer

Durable JSON payload shapes for the app manifest, homepage sections, and the full
tile-type catalog. Get exact CLI flags from `--help`.

App template = project with `useAppHomepage: true`. App instance = a copy users work in.
Manifest = JSON defining the homepage (sections + tiles).

---

## Manifest structure

Set via `dku app-designer set-definition -P PROJ -d @manifest.json` (full replace).

```json
{
  "useAppHomepage": true,
  "label": "My Application",
  "shortDesc": "One-line description shown in the app catalog.",
  "imgColor": "#2a6fa8",
  "imgPattern": 6,
  "instanceFeatures": {
    "showFlowNavLink": true,
    "showGenAiNavLink": false,
    "showLabNavLink": false,
    "showCodeNavLink": false,
    "showSwitchToProjectViewButton": true,
    "showVersionControlFeatures": false
  },
  "instantiationPermission": "USE_APP_MASTER_PERMISSIONS",
  "homepageSections": [
    {
      "sectionTitle": "Step 1) Upload Data",
      "sectionText": "Upload your CSV files below.",
      "visibilityCondition": "",
      "tiles": [ ]
    }
  ]
}
```

### Section fields

| Field | Type | Description |
|-------|------|-------------|
| `sectionTitle` | string | Heading above the section |
| `sectionText` | string | Description; supports HTML and wiki links (`[text](article:ID)`) |
| `visibilityCondition` | string | GREL expression controlling section visibility |
| `tiles` | array | Tile objects |

`sectionTitle` is a plain text header — do **not** also bake the title into
`sectionText` as `<h3>`. `sectionText` is markdown; the only safe HTML escape
hatches are `<i class="icon-warning-sign|icon-info-sign|icon-ok-sign">`, `<br>`,
`<b>` — custom `<div>`/inline styles/color spans are brittle and break on theme
change/clone, so split sections or move rich content to a wiki article instead.
Wiki-link cross-refs need exact, case-sensitive IDs (`Build_All` ≠ `BUILDALL`):
`[label](article:ID)`, `(scenario:ID)`, `(dataset:NAME)`, `(dashboard:ID)`,
`(folder:ID)`, `(recipe:NAME)` — get the id from `dku --format json <noun> list`,
don't guess by uppercasing. `visibilityCondition` gates a param or whole section
against `model.<paramName>`; always pair a toggle param with a `defaultValue` so
new instances render deterministically. Tile prompts: plain imperative voice, no
trailing punctuation (`Upload data`, not `Click to upload!`).

### Instance features (all default `true`)

`showFlowNavLink`, `showGenAiNavLink`, `showLabNavLink`, `showCodeNavLink`,
`showSwitchToProjectViewButton`, `showVersionControlFeatures` (Git controls).
For end-user apps disable all except `showFlowNavLink` and `showSwitchToProjectViewButton`.

### Export manifest (for instances)

Tiles referencing managed folders need those folders copied to instances:

```json
{
  "projectExportManifest": {
    "exportManagedFolders": true,
    "includedManagedFolders": [{"id": "AfVCkm5p", "name": "xpt_export"}]
  }
}
```

Without it, folder tiles in instances fail with "managed folder does not exist".

`instantiationPermission` ∈ `USE_APP_MASTER_PERMISSIONS` (inherit template perms), `EVERYBODY`.

---

## Common tile fields

Every tile inherits: `type` (**required**), `prompt` (label), `help`, `helpTitle`,
`visibilityCondition` (GREL). Dataset tiles also require `datasetName` — without it DSS
opens a blank "New dataset" page instead of erroring.

---

## Tile-type catalog

### Data input

- **`UPLOAD_DATASET_SET_FILE`** — `datasetName` (req), `behavior` (default `GO_TO_DATASET`).
  Behaviors: `GO_TO_DATASET`, `INLINE_UPLOAD_ONLY`, `INLINE_UPLOAD_AND_REDETECT`,
  `INLINE_UPLOAD_REDETECT_AND_INFER` (recommended).
- **`INLINE_DATASET_EDIT`** — `datasetName` (req). Only editable datasets (Filesystem, SQL), not UploadedFiles.
- **`DATASET_EDIT_SETTINGS`** — `datasetName` (req). Edit connection/format settings.
- **`FILES_BASED_DATASET_BROWSE_AND_PREVIEW`** — `datasetName` (req), `behavior`
  (`GO_TO_DATASET`, `INLINE_BROWSE_ONLY`, `INLINE_BROWSE_AND_REDETECT`,
  `INLINE_BROWSE_REDETECT_AND_INFER`, `MODAL_BROWSE_REDETECT_AND_INFER`).
- **`MANAGED_FOLDER_ADD_FILE`** — `folderId`, `behavior` (`GO_TO_FOLDER`, `INLINE_UPLOAD`).
- **`MANAGED_FOLDER_BROWSE`** — `folderId`, `behavior` (`GO_TO_FOLDER`, `INLINE_BROWSE`, `MODAL_BROWSE`).
- **`CONNECTION_EXPLORER_TO_REPLACE_THE_SETTINGS_OF_A_DATASET_WITH_A_NEW_TABLE_REFERENCE`** —
  `datasetName` (req), `behavior` (`GO_TO_DATASET`, `MODAL_BROWSE`). Pick a SQL table, bind to dataset.
- **`STREAMING_ENDPOINT_EDIT_SETTINGS`** — `streamingEndpointId`.

```json
{
  "type": "UPLOAD_DATASET_SET_FILE",
  "datasetName": "raw_input",
  "behavior": "INLINE_UPLOAD_REDETECT_AND_INFER",
  "prompt": "Upload Primary Dataset",
  "help": "Upload a CSV with columns: id, name, date, amount."
}
```

### Action

- **`SCENARIO_RUN`** — `scenarioId`, `buttonText`.
- **`PROJECT_VARIABLES_EDIT`** — `behavior` (`MODAL` default, `INLINE_AUTO_SAVE`,
  `INLINE_EXPLICIT_SAVE`), `buttonText`, `params[]` (form fields, see below), or custom
  UI via `html`/`js`/`module`/`python` (server-side `callPythonDo`).
- **`INLINE_PYTHON_RUN`** — `code`, `buttonText`, `envSelection` (`{envMode}` ∈ `INHERIT`,
  `USE_BUILTIN_MODE`, `EXPLICIT_ENV` + `envName`), `desc` (`{resultType}` ∈ `HTML`,
  `RESULT_TABLE`, `URL`). Frontend scope-chain bug — test in an **instance**, not the template.
- **`PERFORM_SCHEMA_PROPAGATION`** — `datasetName` (optional start), `behavior` (`MANUAL`,
  `AUTO_NO_BUILD`, `AUTO_WITH_BUILDS`), `recipeUpdateOptions`, `excludedRecipes[]`,
  `markAsOkRecipes[]`, `partitionByDim[]`, `partitionByComputable[]`.

```json
{
  "type": "PROJECT_VARIABLES_EDIT",
  "behavior": "INLINE_AUTO_SAVE",
  "prompt": "Matching Parameters",
  "params": [
    {"name": "threshold", "type": "DOUBLE", "label": "Match Threshold", "defaultValue": 0.8},
    {"name": "match_type", "type": "SELECT", "label": "Type", "selectChoices": [
      {"value": "exact", "label": "Exact"}, {"value": "fuzzy", "label": "Fuzzy"}
    ]}
  ]
}
```

### Output

- **`DOWNLOAD_DATASET`** — `datasetName`, `exportParams` (`destinationType` ∈ `DOWNLOAD`,
  `DATASET`, `CUSTOM_MANAGED`; `format.{type,params}`; `selection`).
- **`DOWNLOAD_MANAGED_FOLDER_FILE`** — `folderId`, `itemPath` (optional).
- **`DOWNLOAD_DASHBOARD_EXPORT`** — `dashboardId`, `format` (`paperSize` ∈ `A4`/`A3`/
  `US_LETTER`/`LEDGER`/`SCREEN_16_9`/`CUSTOM`; `orientation` ∈ `LANDSCAPE`/`PORTRAIT`;
  `fileType` ∈ `PDF`/`JPEG`/`PNG`; `width`/`height` for `CUSTOM`).
- **`DOWNLOAD_RMARKDOWN`** — `reportId`, `format` (default `PDF_DOCUMENT`; also
  `HTML_DOCUMENT`, `WORD_DOCUMENT`, `IOSLIDES_PRESENTATION`, `REVEALJS_PRESENTATION`,
  `BEAMER_PRESENTATION`, `FLEX_DASHBOARD`, and other Rmd output formats).
- **`GUESS_TRAIN_DEPLOY`** — `modelId` (req). Hidden from the UI tile picker; CLI/API only.

```json
{
  "type": "DOWNLOAD_DATASET",
  "datasetName": "output_data",
  "prompt": "Download Results (CSV)",
  "exportParams": {
    "destinationType": "DOWNLOAD",
    "temporaryFileBehavior": "AUTO",
    "format": {"type": "csv", "params": {"style": "excel", "charset": "utf8", "separator": ","}},
    "selection": {"samplingMethod": "FULL", "maxRecords": 100000}
  }
}
```

### Navigation & display

- **`DASHBOARD_LINK`** — `dashboardId`.
- **`MANAGED_FOLDER_LINK`** — `folderId`.
- **`IMAGE_DISPLAY`** — `imageId`, `caption`, `ariaLabel`, `maxHeight`.
- **`TEXT_DISPLAY` / `VARIABLE_DISPLAY`** — `content` (HTML). `TEXT_DISPLAY` renders as-is;
  `VARIABLE_DISPLAY` interpolates `${variable_name}` from project variables at runtime
  (fails with "Unknown DSS variable" if missing).

```json
{
  "type": "VARIABLE_DISPLAY",
  "content": "<h3>Study: ${STUDYID}</h3><p>Treatment arms: ${TRT_MAP}</p>"
}
```

---

## Parameter types for `PROJECT_VARIABLES_EDIT`

Each entry in `params[]` maps to a project variable by `name`.

Common fields: `name` (req), `type` (req), `label`, `description`, `defaultValue`,
`mandatory`, `visibilityCondition` (JS, e.g. `"model.use_advanced"`),
`selectChoices` (`[{value, label}]` for SELECT/MULTISELECT), `datasetParamName`
(source DATASET param for DATASET_COLUMN).

- **Basic:** `STRING` (`regexpFilter`), `STRINGS`, `INT` (`minI`/`maxI`), `DOUBLE`
  (`minD`/`maxD`), `DOUBLES`, `BOOLEAN`, `PASSWORD`, `TEXTAREA`, `DATE`.
- **Selection:** `SELECT`/`MULTISELECT` (`selectChoices`, `getChoicesFromPython`), `MAP`,
  `KEY_VALUE_LIST`, `ARRAY`, `OBJECT_LIST` (`subParams`, recursive).
- **Resource pickers:** `DATASET`, `DATASETS`, `DATASET_COLUMN`/`DATASET_COLUMNS`
  (`datasetParamName`, `allowedColumnTypes`), `COLUMN`/`COLUMNS` (`columnRole`),
  `CONNECTION` (`allowedConnectionTypes`)/`CONNECTIONS`, `MANAGED_FOLDER`/`FOLDER`,
  `PROJECT`, `SCENARIO`, `SAVED_MODEL`/`ML_SAVED_MODEL`/`MODEL`, `LLM` (`llmUsagePurpose`),
  `KNOWLEDGE_BANK`, `CODE_ENV`, `CLUSTER` (`clusterPermissions`), `PLUGIN`,
  `PRESET`/`PRESETS` (`parameterSetId`), `API_SERVICE`, `API_SERVICE_VERSION`
  (`apiServiceParamName`), `BUNDLE`, `VISUAL_ANALYSIS`, `ML_TASK`
  (`visualAnalysisParamName`), `MODEL_EVALUATION_STORE`, `CREDENTIAL_REQUEST`
  (`credentialRequestSettings`).
- **Layout:** `SEPARATOR` (label-only divider, no value).

### Patterns

Column picker — hidden `DATASET` param feeds a `DATASET_COLUMN` via `datasetParamName`:

```json
{
  "type": "PROJECT_VARIABLES_EDIT", "behavior": "INLINE_AUTO_SAVE", "prompt": "Column Mapping",
  "params": [
    {"name": "source_ds", "type": "DATASET", "defaultValue": "my_data", "visibilityCondition": "false"},
    {"name": "id_column", "type": "DATASET_COLUMN", "label": "ID Column", "datasetParamName": "source_ds"}
  ]
}
```

Progressive disclosure — gate fields with `visibilityCondition` on a BOOLEAN:

```json
{
  "type": "PROJECT_VARIABLES_EDIT", "behavior": "INLINE_AUTO_SAVE", "prompt": "Advanced",
  "params": [
    {"name": "use_advanced", "type": "BOOLEAN", "label": "Enable advanced options?"},
    {"name": "max_iterations", "type": "INT", "label": "Max iterations", "defaultValue": 100, "visibilityCondition": "model.use_advanced"}
  ]
}
```

---

## UX behaviors

- Number sections as linear steps: upload → configure → run → results.
- Bind every dataset/folder tile to a specific resource (`datasetName`, `folderId`, `dashboardId`).
- Give every tile a `prompt` and `help`.
- Upload tiles: `INLINE_UPLOAD_REDETECT_AND_INFER`. Variable forms: `INLINE_AUTO_SAVE`.
- `SEPARATOR` params to group fields; `visibilityCondition` for progressive disclosure on tiles and sections.
- `VARIABLE_DISPLAY` to surface current config state; `buttonText` on scenario tiles ("Build" beats the scenario ID).
- Hide infra tabs via `instanceFeatures`.
