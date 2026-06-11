# Prompt Recipe — Payload Schema

Complete schema for the `payload` object of a DSS Prompt Recipe, captured from working UI-created recipes.

**Use this doc when**: you're about to call `dku recipe set-settings RECIPE -s @prompt_settings.json` on a recipe created with `dku recipe create -t prompt ...`. The public DSS docs don't cover this schema, so it has to be captured from a working UI-created recipe and documented here.

> **Workflow**: create the recipe shell → `set-settings` with this payload → `dku job run --auto-update-schema`. The `--auto-update-schema` flag is mandatory on first build; `recipe run` alone returns an empty schema. Full sequence: `playbooks/genai-agents.md`.

## Discover the LLM ID first

The `llmId` is instance-specific — every DSS install has a different set of connections and models. **Never hardcode it.** Discover it from the target instance before building the payload:

```bash
# Pick a completion LLM available on this instance
LLM_ID=$(dku --format ids llm list -P PROJ | head -1)
```

The dataset-create steps below use the `filesystem_managed` default managed connection. If your project already has a different default, omit `-c filesystem_managed` and let DSS pick; if you need a non-default connection, discover it with `dku connection list`.

## Minimal working payload (structural example)

The JSON below is the **structure** — the `<placeholder>` values must be substituted with real IDs from the discovery commands above before `set-settings`. See the "Substitution pattern" section after the JSON for how to do that in one shell call.

```json
{
  "payload": {
    "filter": {
      "uiData": {"mode": "&&", "conditions": []},
      "distinct": false,
      "enabled": false
    },
    "rawQueryOutputMode": "RAW_WITHOUT_FULL_IMAGES",
    "completionSettings": {"stopSequences": []},
    "rawResponseOutputMode": "RAW_WITHOUT_TRACES",
    "llmId": "<provider:connection:model>",
    "prompt": {
      "guardrailsPipelineSettings": {"guardrails": []},
      "promptTemplateInputs": [],
      "resultValidation": {
        "requiredJSONObjectKeys": [],
        "expectedFormat": "NONE",
        "forbiddenTerms": []
      },
      "promptTemplateQueriesSource": "DATASET",
      "streamingDisabled": false,
      "chatMessages": {},
      "structuredPromptExamples": [],
      "textPromptTemplate": "Extract the {{field_name}} from this document:\n\n{{content}}",
      "textPromptSystemTemplate": "You return a single JSON object with 'value' and 'source_quote' keys. No prose, no markdown fences.",
      "promptMode": "PROMPT_TEMPLATE_TEXT",
      "textPromptTemplateInputs": [
        {"name": "field_name", "datasetColumnName": "target_field", "type": "TEXT"},
        {"name": "content", "datasetColumnName": "document_content", "type": "TEXT"}
      ]
    },
    "performFiltering": false
  }
}
```

### Substitution pattern

Save the structural JSON above as `prompt_settings.template.json`, then substitute `$LLM_ID` and push:

```bash
jq --arg llm "$LLM_ID" '.payload.llmId = $llm' prompt_settings.template.json > prompt_settings.json
dku recipe set-settings my_recipe -P PROJ -s @prompt_settings.json
```

## Field reference

### Top-level `payload` keys

| Key | Required | Value |
|---|---|---|
| `llmId` | **yes** | LLM ID in `provider:connection:model` format. Discover with `dku --format json llm list -P PROJ`. For agent-as-LLM: `agent:AGENT_ID`. |
| `prompt` | **yes** | The prompt configuration object (see next table). |
| `completionSettings` | no | `{"stopSequences": [], "temperature": 0.7, "maxTokens": 1024}`. Omit for provider defaults. |
| `filter` | no | Pre-LLM row filter. `{"enabled": false, "distinct": false, "uiData": {"mode": "&&", "conditions": []}}` is the inert default. |
| `performFiltering` | no | `false` unless `filter.enabled` is true. |
| `rawQueryOutputMode` | no | Confirmed: `"RAW_WITHOUT_FULL_IMAGES"`. Other values unresearched. |
| `rawResponseOutputMode` | no | Confirmed: `"RAW_WITHOUT_TRACES"`. Other values unresearched. |

### `payload.prompt` keys

| Key | Required | Value |
|---|---|---|
| `promptMode` | **yes** | `"PROMPT_TEMPLATE_TEXT"` (the only mode `dku recipe create-prompt` writes). `"PROMPT_TEMPLATE_STRUCTURED"` exists for chat messages — reachable only via raw `set-settings`, not via `create-prompt`. |
| `textPromptSystemTemplate` | yes (TEXT mode) | System message string. Plain text, no placeholders needed. |
| `textPromptTemplate` | yes (TEXT mode) | User message string with `{{variable}}` placeholders. Each placeholder must have a matching entry in `textPromptTemplateInputs`. |
| `textPromptTemplateInputs` | yes (TEXT mode) | List of `{"name": "var", "datasetColumnName": "col", "type": "TEXT"}`. `name` matches the `{{var}}` placeholder. Use `type: "TEXT"` for all text columns. |
| `promptTemplateQueriesSource` | yes | `"DATASET"` — read one row per input dataset row. (Other values unresearched.) |
| `chatMessages` | no | `{}` unless using `PROMPT_TEMPLATE_STRUCTURED` (not exposed by `create-prompt`; reachable only via raw `set-settings`). |
| `structuredPromptExamples` | no | `[]` unless using few-shot examples in STRUCTURED mode (not exposed by `create-prompt`). |
| `structuredPromptPrefix` | no | Ignored in TEXT mode — may appear on legacy recipes. |
| `resultValidation` | no | See "Result validation" below. |
| `guardrailsPipelineSettings` | no | `{"guardrails": []}` unless attaching guardrails. |
| `streamingDisabled` | no | `false` is the default. Set `true` for batch extraction to avoid token-by-token streaming overhead. |

### `payload.prompt.resultValidation`

| Key | Value |
|---|---|
| `expectedFormat` | **Confirmed valid: `"NONE"`.** `"JSON"` silently deserializes to null and crashes at build time with `NullPointerException: Cannot invoke "...ExpectedFormat.ordinal()" because "resultValidation.expectedFormat" is null`. Other valid enum members not yet researched. Until they are, use `"NONE"` and parse LLM output downstream with a Prepare recipe + JSONFlattener. |
| `requiredJSONObjectKeys` | `[]` — ignored when `expectedFormat` is `"NONE"`. |
| `forbiddenTerms` | `[]` — ignored when unused. |

## Output columns (fixed, always appended)

The Prompt Recipe output dataset always has the **input columns** + these 5 appended:

| Column | Content |
|---|---|
| `llm_output` | The LLM response text. This is the column you read downstream. |
| `llm_validation_status` | Empty when `resultValidation.expectedFormat = "NONE"`. Populated when validation is enabled. |
| `llm_raw_response` | Empty under `rawResponseOutputMode: "RAW_WITHOUT_TRACES"`. Enabled with other modes. |
| `llm_error_message` | Populated only on LLM call failures. |
| `llm_raw_query` | Empty under `rawQueryOutputMode: "RAW_WITHOUT_FULL_IMAGES"`. |

These columns are **not configurable**. To drop the noise columns downstream, use a Prepare recipe with `add-delete-columns`.

## End-to-end: from CSV rows to structured output

```bash
# 0. Discover the LLM ID — do NOT hardcode it (varies per instance)
LLM_ID=$(dku --format ids llm list -P PROJ | head -1) && \

# Setup: create an input dataset of extraction tasks
dku dataset create extraction_tasks --type UploadedFiles -P PROJ && \
dku dataset upload extraction_tasks tasks.csv -P PROJ && \

# 1. Pre-create the output (Prompt Recipes don't auto-create)
dku dataset create extraction_results --type Filesystem -c filesystem_managed -P PROJ && \

# 2. Create the Prompt Recipe shell
dku recipe create extract -t prompt -i extraction_tasks --output-ds extraction_results -P PROJ && \

# 3. Push the payload JSON (with $LLM_ID substituted in from the template — see above)
jq --arg llm "$LLM_ID" '.payload.llmId = $llm' prompt_settings.template.json > prompt_settings.json && \
dku recipe set-settings extract -P PROJ -s @prompt_settings.json && \

# 4. Build with auto-schema (mandatory on first run)
dku job run --target extraction_results -P PROJ --type NON_RECURSIVE_FORCED_BUILD --auto-update-schema --wait && \

# 5. Parse JSON output downstream — no Python recipe needed
dku dataset create extraction_parsed --type Filesystem -c filesystem_managed -P PROJ && \
dku recipe create parse --type prepare -i extraction_results --output-ds extraction_parsed -P PROJ && \
dku recipe add-step parse --type JSONFlattener \
  --params '{"inCol":"llm_output","flattenArrays":false,"maxDepth":2,"nullAsEmpty":true,"prefixOutputs":true,"separator":"_"}' \
  -P PROJ && \
dku recipe add-delete-columns parse \
  --columns "llm_validation_status,llm_raw_response,llm_error_message,llm_raw_query,llm_output" \
  -P PROJ && \
dku job run --target extraction_parsed -P PROJ --type NON_RECURSIVE_FORCED_BUILD --auto-update-schema --wait && \

# 6. Verify
dku dataset head extraction_parsed -P PROJ -n 5
```

## Capturing a payload from a UI-created recipe

If you need fields not documented here (STRUCTURED mode, guardrails, custom completion settings), the fastest way to discover the schema is to create a working recipe in the DSS UI and dump it:

```bash
dku --format json recipe get-settings my_ui_recipe -P PROJ | jq '.payload' > payload_template.json
```

Then diff against the minimal payload above to see what changed, and copy the new fields into your programmatic builder.

## Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `resultValidation.expectedFormat is null` runtime NPE | `"JSON"` or another unknown string was used. Silent server-side deserialization to null. | Use `"NONE"` and parse JSON downstream with a Prepare recipe + JSONFlattener. |
| Output dataset schema is empty after `dku recipe run` | `recipe run` doesn't populate the output schema for Prompt Recipes on first build. | Use `dku job run --target OUT --type NON_RECURSIVE_FORCED_BUILD --auto-update-schema --wait` instead. |
| Recipe created but `--output-ds` complained that output doesn't exist | Generic `dku recipe create -t prompt` does not auto-create outputs (unlike `create-prompt`, which does). | Use `dku recipe create-prompt ...` instead, or pre-create: `dku dataset create NAME --type Filesystem -c filesystem_managed -P PROJ` before `recipe create -t prompt`. |
| `{{variable}}` renders literally in the LLM prompt | Placeholder name doesn't match any entry in `textPromptTemplateInputs`, OR the referenced `datasetColumnName` doesn't exist in the input dataset schema. | Verify both with `dku dataset schema INPUT -P PROJ` and cross-check the `name` field in `textPromptTemplateInputs`. |
| All rows come back with the same generic answer | The prompt template doesn't actually vary per row — either no `{{variable}}` placeholders, or all placeholders reference the same static column. | Add row-varying placeholders. Use `dku dataset head INPUT -n 5` to confirm the input rows actually differ on the referenced columns. |

---

## Critical gotchas

### The user-message template lives in `payload.prompt.textPromptTemplate`, NOT `payload.prompt`
The user prompt template is at `payload.prompt.textPromptTemplate` (with `{{var}}` placeholders), not at `payload.prompt` directly — the latter is the *container* for the whole prompt config. The only `promptMode` `dku recipe create-prompt` writes is `PROMPT_TEMPLATE_TEXT`. `responseFormat: {"type":"json"}` (on `payload.completionSettings`) is distinct from `resultValidation.expectedFormat: "JSON"` — that second form crashes at build time.

### `dku recipe create-prompt` only exposes TEXT mode
`--prompt` writes `payload.prompt.textPromptTemplate` (double-brace `{{var}}`). There is no `--prompt-mode` flag — STRUCTURED / chat / few-shot modes are reachable only via raw `set-settings` with a hand-built payload. Use `--input-var name=column` for placeholder bindings; `--response-format json` sets `payload.completionSettings.responseFormat={"type":"json"}` — distinct from `resultValidation.expectedFormat:JSON` which crashes builds.
