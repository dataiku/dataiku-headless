---
name: agent-tools-reference
description: "Tool type catalog, shared fields, CRUD workflow, and observed config shapes for DSS agent tools."
---

# Agent Tools Reference

Agent tools are project-level objects that agents can call during execution. They represent actions the agent's LLM can invoke — dataset lookups, vector searches, LLM queries, model predictions, custom code, and more.

Agent tools are distinct from MCP tools: they live in the DSS project and are referenced by ID in agent configurations.

## CRUD Workflow

1. **Discover existing tools** — `list_agent_tools(project_key)` returns all tools with their `id`, `name`, `type`, and `description`.
2. **Inspect a tool** — `get_agent_tool_settings(project_key, tool_id)` returns the full raw config. Always do this before creating a new tool of the same type — use the observed config as a template.
3. **Create a tool** — `create_agent_tool(project_key, tool_type, tool_name, tool_id, config)`. The `config` dict is type-specific (see Tool Types below).
4. **Update a tool** — `set_agent_tool_settings(project_key, tool_id, new_settings)`. Full replacement — always call `get_agent_tool_settings` first, modify the returned dict, then pass it back.
5. **Delete a tool** — `delete_agent_tool(project_key, tool_id)`. Confirm with user first — removing a tool referenced by a running agent will break it.

## Shared Top-Level Fields

These fields appear on all tool types and should be set when creating or updating a tool:

| Field | Required | Notes |
|-------|----------|-------|
| `additionalDescriptionForLLM` | recommended | Plain-language description the LLM sees when deciding whether to call this tool. Make it specific — "Use this tool to look up customer info by ID" is better than "Customer lookup". |
| `requireHumanApproval` | no | `true` requires human confirmation before the tool executes. Use for destructive or sensitive actions (e.g. sending emails, appending data). Default: `false`. |
| `allowEditingInputs` | no | Allow end-users to edit tool inputs in the UI. Default: `false`. |
| `singleInstance` | no | Restrict to one concurrent invocation. Default: `false`. |

### Saving tool output to state — the `outputKey` duality

When a block uses `outputMode: "SAVE_TO_STATE"` (on `MANDATORY_TOOL_CALL`, `LLM_REQUEST`, or similar), you must set **both** `outputKey` and `outputStateKey` to the same value.

## Tool Types

### Core (always available)

| Type | Use when |
|------|----------|
| `DatasetRowLookup` | Look up rows from a DSS dataset by key |
| `DatasetRowAppend` | Append rows to a DSS dataset |
| `VectorStoreSearch` | Search a knowledge bank / vector store by semantic similarity |
| `LLMMeshLLMQuery` | Query an LLM or another DSS agent as a sub-task |
| `ClassicalPredictionModelPredict` | Run a deployed ML prediction model on a single record |
| `GRELCalculator` | Evaluate GREL formula expressions (arithmetic, date, geometry, etc.) |
| `InlinePython` | Execute custom Python logic defined inline |
| `RemoteMCPClient` | Call tools exposed by a remote MCP server connection |
| `DataikuReporter` | Send a message via a DSS integration (email, Slack, Teams, etc.) |
| `ApiEndpoint` | Call a DSS API endpoint |

### Plugin/enterprise (require plugin installation or pre-configured connection)

| Type | Use when |
|------|----------|
| `Custom_agent_tool_sql-question-answering-tool_sql-question-answering` | Translate natural language to SQL and query datasets — richer than DatasetRowLookup for multi-table or aggregation queries |
| `Custom_agent_tool_semantic-models-lab_semantic-model-query` | Query a DSS Semantic Model using natural language — uses a pre-built semantic layer for accurate, business-logic-aware SQL generation |
| `Custom_agent_tool_<plugin>_<tool>` | Other plugin-based tools — type string varies by plugin; inspect with `get_agent_tool_settings` |
| Google Search | Web search (requires Google Search connection) |
| Jira / Salesforce / ServiceNow | Enterprise ticketing/CRM integrations (require pre-configured connections) |
| Snowflake Cortex / Databricks Genie | AI-native query over Snowflake or Databricks data (require platform connections) |

Use `list_agent_tools` to see what's already installed in the project.

---

## Type Config Shapes

### DatasetRowLookup

Look up rows in a DSS dataset by column filter.

```json
{
  "params": {
    "datasetRef": "<dataset_name>",
    "retrievalMode": "SINGLE_RECORD",
    "maxRecords": 5,
    "datasetInteractionUserMode": "AS_CALLER_IF_AVAILABLE",
    "usableLookupColumns": ["<column_name>"]
  },
  "additionalDescriptionForLLM": "Use this tool to retrieve <entity> information based on their <key column>."
}
```

| Param | Notes |
|-------|-------|
| `datasetRef` | Dataset name in the project |
| `retrievalMode` | `"SINGLE_RECORD"` (one row) or `"MULTI_RECORD"` (up to `maxRecords`) |
| `maxRecords` | Max rows to return in multi-record mode |
| `datasetInteractionUserMode` | Three options: `"AS_CALLER"` — use end-user's session, hard-fail if none; `"AS_CALLER_IF_AVAILABLE"` — use end-user's session when present, fall back gracefully; `"AS_TOOL_RUNNER"` — always run as the identity of whoever configured the tool, regardless of calling user. Default to `"AS_CALLER_IF_AVAILABLE"` for user-facing agents; use `"AS_TOOL_RUNNER"` for API/automation contexts where no user session exists. |
| `usableLookupColumns` | Columns the agent can filter on — keep this narrow |

**Output shape in state**: row columns flat at the top level — `state["x"]["email"]`, NOT `state["x"]["rows"][0]["email"]`.

---

### DatasetRowAppend

Append a row to a DSS dataset.

```json
{
  "params": {
    "datasetRef": "<dataset_name>"
  },
  "additionalDescriptionForLLM": "Use this tool to append records to the <dataset_name> dataset.",
  "requireHumanApproval": false
}
```

| Param | Notes |
|-------|-------|
| `datasetRef` | Dataset name in the project |

Consider `requireHumanApproval: true` if appending to a sensitive or production dataset.

---

### VectorStoreSearch

Search a knowledge bank using semantic similarity.

```json
{
  "params": {
    "knowledgeBankRef": "<knowledge_bank_id>",
    "searchType": "SIMILARITY",
    "similarityThreshold": 0.5,
    "maxDocuments": 10,
    "retrievalColumns": ["DKU_TEXT_EMBEDDING_COLUMN"],
    "performFiltering": false,
    "allowDynamicFiltering": false,
    "allowAgentInferredFiltering": false,
    "enforceDocumentLevelSecurity": false,
    "includeMultimodalContent": false,
    "includeScore": false,
    "allowEmptyQuery": false,
    "reranking": {
      "enabled": false,
      "maxDocuments": 5
    },
    "sourcesSettings": {
      "snippetFormat": "TEXT",
      "metadataInSources": ["dku_file_path"]
    }
  },
  "additionalDescriptionForLLM": "Use this tool to search through <description of knowledge bank content>."
}
```

| Param | Notes |
|-------|-------|
| `knowledgeBankRef` | Knowledge bank ID — discover with DSS UI or project listing |
| `searchType` | `"SIMILARITY"` (top-k) or `"SIMILARITY_THRESHOLD"` (filter by score) |
| `similarityThreshold` | Min score for `SIMILARITY_THRESHOLD` mode (0–1) |
| `maxDocuments` | Max results to return |
| `reranking.enabled` | Set `true` + `llmId` to rerank results with an LLM |
| `enforceDocumentLevelSecurity` | `true` filters results based on end-user permissions |

---

### LLMMeshLLMQuery

Query an LLM or another DSS agent as a sub-task.

```json
{
  "params": {
    "llmId": "<llm_id>",
    "systemPromptPrepend": "You are an expert in <domain>.",
    "forwardContext": true,
    "returnArtifacts": true,
    "returnSources": true,
    "completionSettings": {
      "stopSequences": [],
      "outputTrajectory": true
    }
  },
  "additionalDescriptionForLLM": "Use this tool to ask questions of <LLM/agent name>."
}
```

| Param | Notes |
|-------|-------|
| `llmId` | LLM identifier — discover with `list_llms` |
| `systemPromptPrepend` | System instructions prepended before the query |
| `forwardContext` | Pass conversation context to the sub-LLM |
| `returnArtifacts` | Include artifacts from the response |
| `returnSources` | Include source citations |

**Output shape in state**: response text (string).

---

### ClassicalPredictionModelPredict

Run a deployed prediction model on a single record.

```json
{
  "params": {
    "smRef": "<saved_model_id>"
  },
  "additionalDescriptionForLLM": "Use this tool to predict <target variable> for a given record. Provide feature values as a dict."
}
```

| Param | Notes |
|-------|-------|
| `smRef` | Saved model ID — discover with `list_saved_models` |

The agent must provide all required feature columns in the `record` input dict.

**Output shape in state**: `{"prediction": ..., "probas": {...}}`.

---

### GRELCalculator

Evaluate GREL formula expressions. No config required — the agent provides the formula as input.

```json
{
  "params": {},
  "additionalDescriptionForLLM": "Use this calculator tool to perform arithmetic, trigonometry, boolean, date, and geometry calculations."
}
```

The agent passes a formula string like `"sqrt(441) * 2"` as input. Supports GREL math, string, date, and geometry functions.

---

### InlinePython

Execute custom Python code defined inline. Implement the `BaseAgentTool` interface.

```json
{
  "params": {
    "code": "import dataiku\nfrom dataiku.llm.agent_tools import BaseAgentTool\n\nclass MyAgentTool(BaseAgentTool):\n    def __init__(self):\n        pass\n\n    def get_descriptor(self, tool):\n        return {\n            \"description\": \"<what this tool does>\",\n            \"inputSchema\": {\n                \"$id\": \"\",\n                \"title\": \"\",\n                \"type\": \"object\",\n                \"properties\": {\n                    \"<param_name>\": {\"type\": \"string\"}\n                },\n                \"required\": [\"<param_name>\"]\n            }\n        }\n\n    def invoke(self, input, trace):\n        args = input[\"input\"]\n        return {\n            \"output\": \"<result string>\",\n            \"sources\": []\n        }\n",
    "codeEnvSelection": {"envMode": "INHERIT"},
    "containerExecSelection": {"containerMode": "INHERIT"},
    "dependencies": []
  }
}
```

| Param | Notes |
|-------|-------|
| `code` | Full Python source; must define a class extending `BaseAgentTool` with `get_descriptor()` and `invoke()` |
| `codeEnvSelection.envMode` | `"INHERIT"` uses project default code env |
| `dependencies` | List of additional pip packages |

The `get_descriptor()` return value is what the LLM sees — write a clear `description` and an accurate `inputSchema`.

**Output shape in state**: whatever `invoke()` returns under `"output"` — often a JSON string; use `parse_json` before subscripting.

---

### RemoteMCPClient

Connect to an external MCP server and expose its tools to the agent.

```json
{
  "params": {
    "connectionName": "<mcp_connection_name>",
    "subtoolsStateOverride": {
      "<subtool_name>": true
    },
    "imageHandlingMode": "ONLY_ADD_AS_ARTIFACT"
  },
  "additionalDescriptionForLLM": "Use this tool to <description of what the MCP server provides>."
}
```

| Param | Notes |
|-------|-------|
| `connectionName` | DSS connection name for the MCP server |
| `subtoolsStateOverride` | Map of subtool name → enabled (`true`/`false`). Use to expose only specific subtools. |
| `imageHandlingMode` | How to handle image responses: `"ONLY_ADD_AS_ARTIFACT"` |

The MCP connection must be configured in DSS administration before referencing it here.

**Output shape in state**: varies by subtool — inspect with a smoke test.

---

### DataikuReporter

Send a message via a DSS integration (email, Slack, Teams, etc.).

```json
{
  "params": {
    "integration": {
      "type": "mail-direct",
      "configuration": {
        "subject": "<email subject>",
        "messageSource": "INLINE",
        "templateFormat": "FREEMARKER",
        "sendAsHTML": true,
        "message": "<html body with ${message} placeholder>",
        "channelId": "<smtp_channel_id>",
        "sender": "<sender@example.com>",
        "recipient": "<recipient@example.com>"
      }
    },
    "variables": [
      {
        "id": "message",
        "sourceType": "TOOL_INPUT",
        "toolInputDescription": "The message to send"
      }
    ]
  },
  "additionalDescriptionForLLM": "Use this tool to send an email.",
  "requireHumanApproval": true
}
```

| Param | Notes |
|-------|-------|
| `integration.type` | Integration type (e.g. `"mail-direct"`, Slack, Teams) |
| `integration.configuration.channelId` | DSS messaging channel ID — must be pre-configured in DSS administration |
|`integration.configuration.<field>` | Fixed at configure time unless referenced as `${field}` and declared in variables with `sourceType: "TOOL_INPUT"`. Hard-code sensitive fields (e.g. `recipient: "user@example.com"`) to prevent LLM override; use `recipient: "${recipient}"` + a matching variable entry to let the LLM supply it.|
| `variables` | Maps tool inputs to template variables. `sourceType: "TOOL_INPUT"` means the LLM provides the value. |
| `requireHumanApproval` | Strongly recommended `true` for any messaging tool |

---

### ApiEndpoint

Call a DSS API endpoint. Config is minimal — endpoint details are configured via DSS administration.

```json
{
  "params": {},
  "additionalDescriptionForLLM": "Use this tool to query a RESTful API endpoint."
}
```

---

### SQL Question Answering (plugin)

Translates natural language questions into SQL, runs them against one or more DSS datasets, and returns results. Requires the SQL Question Answering plugin and a database connection.

```json
{
  "type": "Custom_agent_tool_sql-question-answering-tool_sql-question-answering",
  "params": {
    "config": {
      "datasets": ["<dataset_name_1>", "<dataset_name_2>"],
      "connection": "<dss_connection_name>",
      "llmId": "<llm_id>",
      "additionalInformation": "Context about what these tables contain and how they relate.",
      "hard_sql_limit": 200,
      "return_value_mode": "AUTO",
      "enduser_sql_execution": "tool_user",
      "sample_values_strategy": "FROM_DATA",
      "sample_values_from_data_cardinality_cutoff": 30,
      "include_column_names_in_descriptor": true,
      "include_column_descriptions_in_descriptor": true,
      "max_records_for_artifact": -1
    },
    "containerExecSelection": {"containerMode": "INHERIT"}
  },
  "additionalDescriptionForLLM": "Use this tool to answer questions about <describe the data>."
}
```

| Param | Notes |
|-------|-------|
| `datasets` | Dataset names in the project to query |
| `connection` | DSS connection name for the underlying database |
| `llmId` | LLM used to generate SQL — discover with `list_llms` |
| `additionalInformation` | Plain-language context about the tables; improves SQL generation accuracy |
| `hard_sql_limit` | Max rows the SQL may return |
| `return_value_mode` | `"AUTO"` (default, LLM chooses) / `"ANSWER"` (prose text only) / `"ARTIFACT"` (raw row data only) / `"BOTH"`. **Critical for downstream state parsing** — AUTO and ANSWER return prose that cannot be parsed by `SET_STATE_ENTRIES` or CEL. When this tool feeds a downstream deterministic block (e.g. the SQL rows go through a SET_STATE_ENTRIES to extract into top-level state keys), set to `"ARTIFACT"`. |
| `enduser_sql_execution` | `"tool_user"` runs SQL as the calling user (respects permissions) |

**Output shape in state**: prose string by default (`AUTO`/`ANSWER`). Use `return_value_mode: "ARTIFACT"` for structured rows when downstream CEL/`SET_STATE_ENTRIES` needs to subscript the result.

---

### Semantic Model Query (plugin)

Queries a DSS Semantic Model using natural language. The semantic layer handles business logic, joins, and metric definitions — more accurate than raw SQL generation for governed data. Requires the Semantic Models Lab plugin.

```json
{
  "type": "Custom_agent_tool_semantic-models-lab_semantic-model-query",
  "params": {
    "config": {
      "project_key": "<project_key>",
      "semantic_model_id": "<semantic_model_id>",
      "llm_id": "<llm_id>",
      "embedding_llm_id": "<embedding_llm_id>",
      "sql_generation_mode": "VERSION",
      "version_number": "",
      "agent_mode": false,
      "max_rows_per_query": 1000,
      "artifacts_records_limit": 1000,
      "sources_records_limit": 50,
      "agent_recursion_limit": 100,
      "enduser_sql_execution": "enduser_available"
    },
    "containerExecSelection": {"containerMode": "INHERIT"}
  },
  "additionalDescriptionForLLM": "Use this tool to query <describe the domain> data through the semantic model."
}
```

| Param | Notes |
|-------|-------|
| `semantic_model_id` | ID of the Semantic Model object in DSS |
| `project_key` | Project containing the semantic model |
| `llm_id` | LLM for SQL generation — discover with `list_llms` |
| `embedding_llm_id` | Embedding model for semantic search within the model |
| `sql_generation_mode` | `"VERSION"` uses a pinned version of the semantic model |
| `enduser_sql_execution` | `"enduser_available"` runs queries as the calling user |

**When to prefer over SQL Question Answering**: use Semantic Model Query when a semantic model already exists for the domain — it leverages pre-defined business logic and metrics. Use SQL Question Answering when querying ad-hoc datasets without a semantic layer.

---

### Custom Plugin Tools

Plugin-based tools have a type string of the form `Custom_agent_tool_<plugin-id>_<tool-id>`. The `params.config` shape is entirely defined by the plugin.

```json
{
  "type": "Custom_agent_tool_<plugin-id>_<tool-id>",
  "params": {
    "config": {
      "<plugin_param_1>": "<value>",
      "<plugin_param_2>": "<value>"
    },
    "containerExecSelection": {"containerMode": "INHERIT"}
  },
  "additionalDescriptionForLLM": "Use this tool to <describe the plugin tool's purpose>."
}
```

Always inspect an existing tool of this type with `get_agent_tool_settings` to discover the correct `params.config` shape — it varies by plugin.

**Output shape in state**: varies by plugin — inspect with a smoke test.

---

## Attaching Tools to Agents

Tools are referenced by their `id`:

- **Simple agent** — pass `tool_ids` to `update_agent_settings`. `tool_ids` **replaces** the full list — include all tools you want active.
- **Structured agent blocks** — reference tools in block `tools` arrays using the tool object shape (see [standard_react reference](block-types/standard_react.md) for the full tool object shape).

## Guardrails

1. **Discover before creating.** Use `list_agent_tools` first — the tool you need may already exist.
2. **Inspect before templating.** Use `get_agent_tool_settings` on an existing tool of the same type to get the correct config shape.
3. **Always set `additionalDescriptionForLLM`.** This is the primary signal the LLM uses to select and invoke tools correctly. Vague descriptions lead to missed or incorrect tool calls.
4. **Use `requireHumanApproval: true` for destructive or external actions** — especially `DataikuReporter` (messaging) and `DatasetRowAppend` on production data.
5. **`requireHumanApproval` cannot be used inside FOR_EACH, PARALLEL, or REFLECTION sub-sequences.** Tools with human approval will fail if the calling block is inside one of these containers. Keep human-approval tools in the main flow only.
6. **IDs are stable; names are not.** Reference tools by `id` in agent configs.
7. **Deleting a referenced tool breaks the agent.** Confirm with the user before deleting any tool that may be in use.
