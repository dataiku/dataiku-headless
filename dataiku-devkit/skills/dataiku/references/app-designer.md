# App Designer Reference

> Complete reference for building Dataiku DSS applications with the App Designer. Covers manifest structure, all 21 tile types, 40+ parameter types, section design, and UX patterns from production apps.
>
> Source of truth: `com.dataiku.dip.coremodel.AppHomepageTile.java` and `AppManifest.java`.

---

## Overview

The App Designer turns a DSS project into a self-service application. End users interact through a homepage of **tiles** organized in **sections**, without needing to understand the flow, recipes, or code behind it.

**Key concepts:**
- **App template** — the project with `useAppHomepage: true`
- **App instance** — a copy created from the template; users work here
- **Manifest** — JSON config defining the homepage layout (sections + tiles)
- **Tiles** — interactive components (forms, buttons, uploads, downloads, displays)
- **Sections** — groups of tiles with title, description text, and optional visibility condition

---

## CLI Quick Reference

```bash
# Enable app mode
dku app-designer enable -P PROJ --label "My App" --description "What it does"

# Set section titles (creates sections if needed)
dku app-designer set-section -P PROJ -s 0 --title "Step 1) Upload Data" --text "Upload your CSV files here."
dku app-designer set-section -P PROJ -s 1 --title "Step 2) Configure" --text "Set matching parameters."

# Add tiles with shortcuts
dku app-designer add-tile -P PROJ -s 0 --type UPLOAD_DATASET_SET_FILE --dataset raw_input --behavior INLINE_UPLOAD_REDETECT_AND_INFER --prompt "Upload Data"
dku app-designer add-tile -P PROJ -s 1 --type SCENARIO_RUN --scenario BUILD --prompt "Run Pipeline" --button-text "Build"
dku app-designer add-tile -P PROJ -s 1 --type DASHBOARD_LINK --dashboard dash123 --prompt "View Results"
dku app-designer add-tile -P PROJ -s 1 --type DOWNLOAD_DATASET --dataset output --prompt "Download Results"

# Add complex tiles via JSON
dku app-designer add-tile -P PROJ -s 1 --definition @tile.json

# Full manifest replacement
dku app-designer set-definition -P PROJ -d @manifest.json

# Inspect
dku app-designer list-tiles -P PROJ
dku app-designer get -P PROJ -o json

# App instances
dku app list
dku app create-instance PROJECT_PROJ --key INST1 --name "Instance 1"
```

---

## Manifest Structure

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
      "tiles": [ ... ]
    }
  ]
}
```

### Section Fields

| Field | Type | Description |
|-------|------|-------------|
| `sectionTitle` | string | Heading displayed above the section |
| `sectionText` | string | Description text; supports HTML and wiki links (`[text](article:ID)`) |
| `visibilityCondition` | string | GREL expression controlling section visibility (e.g., `"model.show_advanced"`) |
| `tiles` | array | Array of tile objects |

### Instance Features

| Feature | Default | Description |
|---------|---------|-------------|
| `showFlowNavLink` | `true` | Show Flow tab |
| `showGenAiNavLink` | `true` | Show GenAI tab |
| `showLabNavLink` | `true` | Show Lab tab |
| `showCodeNavLink` | `true` | Show Code tab |
| `showSwitchToProjectViewButton` | `true` | Allow switching to full project view |
| `showVersionControlFeatures` | `true` | Show Git controls |

**Tip:** For end-user apps, disable everything except `showFlowNavLink` and `showSwitchToProjectViewButton`.

### Instantiation Permissions

| Value | Description |
|-------|-------------|
| `USE_APP_MASTER_PERMISSIONS` | Instance inherits template project permissions |
| `EVERYBODY` | Any user can create instances |

---

## Common Tile Fields

Every tile type inherits these fields:

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | **Required.** One of the 21 tile types below |
| `prompt` | string | Label shown to the user |
| `help` | string | Help text (shown via help button) |
| `helpTitle` | string | Title for the help modal |
| `visibilityCondition` | string | GREL expression controlling tile visibility |

---

## All 21 Tile Types

### Data Input Tiles (8 types)

#### `UPLOAD_DATASET_SET_FILE`

Upload a file to a dataset.

| Field | Type | Default |
|-------|------|---------|
| `datasetName` | string | — (user picks from list) |
| `behavior` | enum | `GO_TO_DATASET` |

**Behaviors:**

| Value | Description |
|-------|-------------|
| `GO_TO_DATASET` | Navigate to the dataset page |
| `INLINE_UPLOAD_ONLY` | Upload inline, no re-detection |
| `INLINE_UPLOAD_AND_REDETECT` | Upload inline, re-detect format |
| `INLINE_UPLOAD_REDETECT_AND_INFER` | Upload inline, re-detect format and infer schema **(recommended)** |

```json
{
  "type": "UPLOAD_DATASET_SET_FILE",
  "datasetName": "raw_input",
  "behavior": "INLINE_UPLOAD_REDETECT_AND_INFER",
  "prompt": "Upload Primary Dataset",
  "help": "Upload a CSV file with columns: id, name, date, amount."
}
```

#### `INLINE_DATASET_EDIT`

Edit dataset rows inline (editable/inline datasets).

| Field | Type |
|-------|------|
| `datasetName` | string |

```json
{
  "type": "INLINE_DATASET_EDIT",
  "datasetName": "STUDY_CONFIG",
  "prompt": "Edit Study Configuration",
  "help": "Edit the key-value pairs controlling the pipeline."
}
```

#### `DATASET_EDIT_SETTINGS`

Edit dataset connection/format settings.

| Field | Type |
|-------|------|
| `datasetName` | string |

#### `FILES_BASED_DATASET_BROWSE_AND_PREVIEW`

Browse and preview a file-based dataset.

| Field | Type | Default |
|-------|------|---------|
| `datasetName` | string | — |
| `behavior` | enum | `GO_TO_DATASET` |

**Behaviors:** `GO_TO_DATASET`, `INLINE_BROWSE_ONLY`, `INLINE_BROWSE_AND_REDETECT`, `INLINE_BROWSE_REDETECT_AND_INFER`, `MODAL_BROWSE_REDETECT_AND_INFER`

#### `MANAGED_FOLDER_ADD_FILE`

Upload file to a managed folder.

| Field | Type | Default |
|-------|------|---------|
| `folderId` | string | — (user picks from list) |
| `behavior` | enum | `GO_TO_FOLDER` |

**Behaviors:** `GO_TO_FOLDER`, `INLINE_UPLOAD`

```json
{
  "type": "MANAGED_FOLDER_ADD_FILE",
  "folderId": "a1nNMMb9",
  "behavior": "INLINE_UPLOAD",
  "prompt": "Upload Workflow Files"
}
```

#### `MANAGED_FOLDER_BROWSE`

Browse managed folder contents.

| Field | Type | Default |
|-------|------|---------|
| `folderId` | string | — |
| `behavior` | enum | `GO_TO_FOLDER` |

**Behaviors:** `GO_TO_FOLDER`, `INLINE_BROWSE`, `MODAL_BROWSE`

#### `CONNECTION_EXPLORER_TO_REPLACE_THE_SETTINGS_OF_A_DATASET_WITH_A_NEW_TABLE_REFERENCE`

Browse a SQL connection to pick a table and bind it to a dataset.

| Field | Type | Default |
|-------|------|---------|
| `datasetName` | string | — |
| `behavior` | enum | `GO_TO_DATASET` |

**Behaviors:** `GO_TO_DATASET`, `MODAL_BROWSE`

#### `STREAMING_ENDPOINT_EDIT_SETTINGS`

Edit settings of a streaming endpoint.

| Field | Type |
|-------|------|
| `streamingEndpointId` | string |

---

### Action Tiles (4 types)

#### `SCENARIO_RUN`

Run a scenario.

| Field | Type |
|-------|------|
| `scenarioId` | string |
| `buttonText` | string |

```json
{
  "type": "SCENARIO_RUN",
  "scenarioId": "BUILD_PIPELINE",
  "buttonText": "Build",
  "prompt": "Build Full Pipeline",
  "help": "Runs all steps: ingest, transform, validate, export."
}
```

#### `PROJECT_VARIABLES_EDIT`

Edit project variables via a form, or render a fully custom UI with HTML/JS/Python.

| Field | Type | Default |
|-------|------|---------|
| `behavior` | enum | `MODAL` |
| `buttonText` | string | — |
| `params` | array of ParamDesc | `[]` |
| `html` | string | — (custom UI mode) |
| `js` | string | — (custom UI mode) |
| `module` | string | — (Angular module name for custom UI) |
| `python` | string | — (server-side `callPythonDo` callback) |

**Behaviors:** `MODAL`, `INLINE_AUTO_SAVE`, `INLINE_EXPLICIT_SAVE`

**Standard mode** — use `params` to define form fields:

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

**Custom UI mode** — use `html`/`js`/`module`/`python` for a fully custom Angular component with server-side Python callbacks (advanced, see GOVERNMETADATA example).

See [Parameter Types](#parameter-types-for-project_variables_edit) section for the full `ParamDesc` spec.

#### `INLINE_PYTHON_RUN`

Run inline Python code and display results.

| Field | Type | Default |
|-------|------|---------|
| `code` | string | — |
| `buttonText` | string | — |
| `envSelection` | object | `{"envMode": "INHERIT"}` |
| `desc` | object | `{"resultType": "HTML"}` |

**`envSelection.envMode`:** `INHERIT`, `USE_BUILTIN_MODE`, `EXPLICIT_ENV` (with `envName`)

**`desc.resultType`:** `HTML`, `RESULT_TABLE`, `URL`

```json
{
  "type": "INLINE_PYTHON_RUN",
  "code": "from dataiku.runnables import Runnable, ResultTable\n\nclass MyCode(Runnable):\n    def __init__(self, project_key, config, plugin_config):\n        self.project_key = project_key\n    def get_progress_target(self):\n        return None\n    def run(self, progress_callback):\n        rt = ResultTable()\n        rt.add_column('status', 'Status', 'STRING')\n        rt.add_record(['OK'])\n        return rt",
  "buttonText": "Check",
  "prompt": "Validate Connections",
  "desc": {"impersonate": true, "resultType": "RESULT_TABLE", "params": [], "adminParams": []},
  "envSelection": {"envMode": "INHERIT"}
}
```

#### `PERFORM_SCHEMA_PROPAGATION`

Propagate schema changes downstream.

| Field | Type | Default |
|-------|------|---------|
| `datasetName` | string | — (starting point, optional) |
| `behavior` | enum | `MANUAL` |
| `recipeUpdateOptions` | object | `{}` |
| `excludedRecipes` | array of string | `[]` |
| `markAsOkRecipes` | array of string | `[]` |
| `partitionByDim` | array | `[]` |
| `partitionByComputable` | array | `[]` |

**Behaviors:** `MANUAL`, `AUTO_NO_BUILD`, `AUTO_WITH_BUILDS`

---

### Output Tiles (5 types)

#### `DOWNLOAD_DATASET`

Download a dataset as a file.

| Field | Type | Default |
|-------|------|---------|
| `datasetName` | string | — (user picks from list) |
| `exportParams` | object | CSV tab-separated |

```json
{
  "type": "DOWNLOAD_DATASET",
  "datasetName": "output_data",
  "prompt": "Download Results (CSV)",
  "exportParams": {
    "destinationType": "DOWNLOAD",
    "temporaryFileBehavior": "AUTO",
    "format": {
      "type": "csv",
      "params": {
        "style": "excel", "charset": "utf8", "separator": ",",
        "quoteChar": "\"", "escapeChar": "\\",
        "dateSerializationFormat": "ISO", "arrayMapFormat": "json"
      }
    },
    "selection": {"samplingMethod": "FULL", "maxRecords": 100000}
  }
}
```

**`exportParams.destinationType`:** `DOWNLOAD`, `DATASET`, `CUSTOM_MANAGED`

#### `DOWNLOAD_MANAGED_FOLDER_FILE`

Download a file from a managed folder.

| Field | Type |
|-------|------|
| `folderId` | string |
| `itemPath` | string (optional — specific file path within folder) |

#### `DOWNLOAD_DASHBOARD_EXPORT`

Export a dashboard as PDF/PNG/JPEG.

| Field | Type |
|-------|------|
| `dashboardId` | string |
| `format` | object |

**`format` fields:**

| Field | Values |
|-------|--------|
| `paperSize` | `A4`, `A3`, `US_LETTER`, `LEDGER`, `SCREEN_16_9`, `CUSTOM` |
| `orientation` | `LANDSCAPE`, `PORTRAIT` |
| `fileType` | `PDF`, `JPEG`, `PNG` |
| `width` | integer (for `CUSTOM` paper size) |
| `height` | integer (for `CUSTOM` paper size) |

```json
{
  "type": "DOWNLOAD_DASHBOARD_EXPORT",
  "dashboardId": "d6SHKw5",
  "prompt": "Download Dashboard PDF",
  "format": {"paperSize": "A4", "orientation": "LANDSCAPE", "fileType": "PDF"}
}
```

#### `DOWNLOAD_RMARKDOWN`

Download an R Markdown report.

| Field | Type | Default |
|-------|------|---------|
| `reportId` | string | — |
| `format` | enum | `PDF_DOCUMENT` |

**Format values:** `HTML_DOCUMENT`, `PDF_DOCUMENT`, `HTML_NOTEBOOK`, `WORD_DOCUMENT`, `ODT_DOCUMENT`, `RTF_DOCUMENT`, `IOSLIDES_PRESENTATION`, `REVEALJS_PRESENTATION`, `SLIDY_PRESENTATION`, `BEAMER_PRESENTATION`, `FLEX_DASHBOARD`, `TUFTE_HANDOUT`, `TUFTE_HTML`, `TUFTE_BOOK`, `HTML_VIGNETTE`

#### `GUESS_TRAIN_DEPLOY`

Auto-ML tile: guess features, train model, deploy to flow.

| Field | Type |
|-------|------|
| `modelId` | string |

---

### Navigation & Display Tiles (4 types)

#### `DASHBOARD_LINK`

Link to a dashboard.

| Field | Type |
|-------|------|
| `dashboardId` | string |

```json
{
  "type": "DASHBOARD_LINK",
  "dashboardId": "aRLxNwn",
  "prompt": "View Reconciliation Analysis"
}
```

#### `MANAGED_FOLDER_LINK`

Link to a managed folder.

| Field | Type |
|-------|------|
| `folderId` | string |

#### `IMAGE_DISPLAY`

Display an image.

| Field | Type |
|-------|------|
| `imageId` | string |
| `caption` | string |
| `ariaLabel` | string |
| `maxHeight` | integer |

#### `TEXT_DISPLAY` / `VARIABLE_DISPLAY`

Display static text or text with interpolated project variables. Both use the same structure.

| Field | Type |
|-------|------|
| `content` | string (HTML) |

- `TEXT_DISPLAY` — renders `content` as-is (static HTML)
- `VARIABLE_DISPLAY` — interpolates `${variable_name}` references in `content` with project variable values at runtime

```json
{
  "type": "VARIABLE_DISPLAY",
  "content": "<h3>Study: ${STUDYID}</h3><p>Treatment arms: ${TRT_MAP}</p>"
}
```

---

## Parameter Types for `PROJECT_VARIABLES_EDIT`

The `params` array defines form fields. Each param maps to a project variable by `name`.

### Common Param Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | **Required.** Variable name (maps to project variable) |
| `type` | string | **Required.** One of the types below |
| `label` | string | Display label in the form |
| `description` | string | Help text below the field |
| `defaultValue` | any | Default value |
| `mandatory` | boolean | Whether the field is required |
| `visibilityCondition` | string | JS expression controlling visibility (e.g., `"model.use_advanced"`) |
| `selectChoices` | array | `[{value, label}]` for SELECT/MULTISELECT |
| `datasetParamName` | string | Name of a DATASET param to source columns from (for DATASET_COLUMN) |

### All Parameter Types

#### Basic Types

| Type | Description | Extra Fields |
|------|-------------|-------------|
| `STRING` | Text input | `regexpFilter` |
| `STRINGS` | List of strings | |
| `INT` | Integer input | `minI`, `maxI` |
| `DOUBLE` | Decimal input | `minD`, `maxD` |
| `DOUBLES` | List of decimals | |
| `BOOLEAN` | Checkbox | |
| `PASSWORD` | Password field | |
| `TEXTAREA` | Multi-line text | |
| `DATE` | Date picker | |

#### Selection Types

| Type | Description | Extra Fields |
|------|-------------|-------------|
| `SELECT` | Dropdown | `selectChoices: [{value, label}]`, `getChoicesFromPython` |
| `MULTISELECT` | Multi-select | `selectChoices`, `getChoicesFromPython` |
| `MAP` | Key-value map | |
| `KEY_VALUE_LIST` | List of key-value pairs | |
| `ARRAY` | Array of values | |
| `OBJECT_LIST` | List of objects | `subParams` (recursive) |

#### DSS Resource Pickers

| Type | Description | Extra Fields |
|------|-------------|-------------|
| `DATASET` | Dataset picker | |
| `DATASETS` | Multi-dataset picker | |
| `DATASET_COLUMN` | Column picker (from dataset) | `datasetParamName`, `allowedColumnTypes` |
| `DATASET_COLUMNS` | Multi-column picker | `datasetParamName`, `allowedColumnTypes` |
| `COLUMN` | Generic column picker | `columnRole` |
| `COLUMNS` | Generic multi-column picker | `columnRole` |
| `CONNECTION` | Connection picker | `allowedConnectionTypes` |
| `CONNECTIONS` | Multi-connection picker | |
| `MANAGED_FOLDER` / `FOLDER` | Folder picker | |
| `PROJECT` | Project picker | |
| `SCENARIO` | Scenario picker | |
| `SAVED_MODEL` / `ML_SAVED_MODEL` / `MODEL` | Model picker | |
| `LLM` | LLM picker | `llmUsagePurpose` |
| `KNOWLEDGE_BANK` | Knowledge bank picker | |
| `CODE_ENV` | Code environment picker | |
| `CLUSTER` | Cluster picker | `clusterPermissions` |
| `PLUGIN` | Plugin picker | |
| `PRESET` / `PRESETS` | Plugin preset picker | `parameterSetId` |
| `API_SERVICE` | API service picker | |
| `API_SERVICE_VERSION` | API service version picker | `apiServiceParamName` |
| `BUNDLE` | Bundle picker | |
| `VISUAL_ANALYSIS` | Visual analysis picker | |
| `ML_TASK` | ML task picker | `visualAnalysisParamName` |
| `MODEL_EVALUATION_STORE` | Model evaluation store picker | |
| `CREDENTIAL_REQUEST` | Credential request | `credentialRequestSettings` |

#### Layout Type

| Type | Description |
|------|-------------|
| `SEPARATOR` | Visual section divider (label-only, no value) |

### Key Patterns

#### Column Picker (hidden dataset + DATASET_COLUMN)

```json
{
  "type": "PROJECT_VARIABLES_EDIT",
  "behavior": "INLINE_AUTO_SAVE",
  "prompt": "Column Mapping",
  "params": [
    {"name": "source_ds", "type": "DATASET", "defaultValue": "my_data", "visibilityCondition": "false"},
    {"name": "sep1", "type": "SEPARATOR", "label": "Source Columns"},
    {"name": "id_column", "type": "DATASET_COLUMN", "label": "ID Column", "datasetParamName": "source_ds"},
    {"name": "date_column", "type": "DATASET_COLUMN", "label": "Date Column", "datasetParamName": "source_ds"}
  ]
}
```

#### Progressive Disclosure (visibilityCondition)

```json
{
  "type": "PROJECT_VARIABLES_EDIT",
  "behavior": "INLINE_AUTO_SAVE",
  "prompt": "Advanced Options",
  "params": [
    {"name": "use_advanced", "type": "BOOLEAN", "label": "Enable advanced options?"},
    {"name": "sep_adv", "type": "SEPARATOR", "label": "Advanced", "visibilityCondition": "model.use_advanced"},
    {"name": "max_iterations", "type": "INT", "label": "Max iterations", "defaultValue": 100, "visibilityCondition": "model.use_advanced"}
  ]
}
```

#### Select with Choices

```json
{
  "name": "match_type", "type": "SELECT", "label": "Match Type",
  "selectChoices": [
    {"value": "exact", "label": "Exact Match"},
    {"value": "fuzzy", "label": "Fuzzy Match"},
    {"value": "phonetic", "label": "Phonetic Match"}
  ]
}
```

---

## UX Design Patterns

### Pattern 1: Step-by-Step Workflow

The most effective app layout. Number sections explicitly and guide users through a linear workflow.

```
Section 0: Header (title + overview text, no tiles — or TEXT_DISPLAY tile)
Section 1: Step 1) Upload Data (UPLOAD_DATASET_SET_FILE tiles)
Section 2: Step 2) Configure (PROJECT_VARIABLES_EDIT forms)
Section 3: Step 3) Run (SCENARIO_RUN + PERFORM_SCHEMA_PROPAGATION)
Section 4: Step 4) Results (DASHBOARD_LINK + DOWNLOAD_DATASET)
```

### Pattern 2: Alternative Paths

When users can choose between methods (e.g., upload vs. database connection):

```
Section 1: "Option 1 — Upload" (sectionText: "To use a database, skip to next section")
Section 2: "Option 2 — Database" (sectionText: "To upload files, go back")
```

### Pattern 3: Dynamic Content with VARIABLE_DISPLAY

Show project state directly in the app homepage:

```json
{
  "type": "VARIABLE_DISPLAY",
  "content": "<div style='padding:12px; background:#f0f7ff; border-radius:4px'><b>Current study:</b> ${STUDYID}<br><b>Treatment arms:</b> ${TRT_MAP}</div>"
}
```

### Pattern 4: Image Branding

Add a logo or diagram at the top:

```json
{
  "type": "IMAGE_DISPLAY",
  "imageId": "logo",
  "caption": "Powered by Dataiku",
  "maxHeight": 80
}
```

### Design Checklist

1. **Every section has a title** — numbered steps for linear workflows
2. **Every tile has a prompt** — never leave prompts empty
3. **Bind tiles to specific resources** — `datasetName`, `folderId`, `dashboardId`
4. **Use `help` text** — explain what each tile does and what the user should expect
5. **Use `INLINE_UPLOAD_REDETECT_AND_INFER`** for upload tiles — best UX
6. **Use `INLINE_AUTO_SAVE`** for variable edit forms — saves without modal
7. **Use SEPARATOR params** to visually group related fields
8. **Use `visibilityCondition`** for progressive disclosure — on both tiles and sections
9. **Hide infrastructure** — disable Code/Lab/GenAI tabs via `instanceFeatures`
10. **Use `buttonText`** on scenario tiles — "Build" is better than the scenario ID
11. **Use `VARIABLE_DISPLAY`** to show current config state on the homepage
12. **Use `TEXT_DISPLAY`** for instructions or warnings that don't need variable interpolation

### Anti-Patterns

| Anti-pattern | Fix |
|-------------|-----|
| Generic tiles without `datasetName` | Always bind to the specific dataset |
| No section titles | Add `sectionTitle` to every section |
| Empty prompts | Add descriptive `prompt` to every tile |
| All features visible | Disable unnecessary `instanceFeatures` |
| One giant section | Split into numbered steps |
| No help text | Add `help` explaining what the tile does |
| MODAL behavior for frequent edits | Use `INLINE_AUTO_SAVE` instead |
| Upload with `GO_TO_DATASET` | Use `INLINE_UPLOAD_REDETECT_AND_INFER` |
| Hardcoded text that should reflect variables | Use `VARIABLE_DISPLAY` with `${var}` |
