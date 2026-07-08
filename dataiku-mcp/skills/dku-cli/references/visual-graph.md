# Reference: Visual Graph (Kuzu plugin)

Graph analytics via the Visual Graph plugin (DSS 14+). Built-in engine is **Kuzu**
(Cypher). Plugin surfaces evolve faster than core DSS — when the live UI disagrees
with this file, trust the UI.

## Surfaces

- The graph **Editor** and **Explorer** are **Visual Webapps** (New webapp →
  Visual Webapp → search "graph") — not a project menu item, not standard recipes.
- The webapp backend must run with **Container = None**: the plugin code env has no
  built container image, and a containerized backend crashes with an EMPTY log.

## Editor configuration

- Node/edge source datasets; a node group can span several datasets
  (multi-definition).
- Database: **Built-in** (Kuzu) or Neo4j. Optional AI assistant: an LLM + a SQL
  history dataset.
- Saving/publishing requires a **saved-configuration dataset**, a **publish
  connection** (managed-folder connection), and an internal storage dataset.

## Build & publish

- Node group: label / dataset / unique-id column / name column / properties.
  Edge group: label / source+target node group / dataset / source+target id columns.
- Save configuration → **Publish** creates a `build-graph` recipe plus a managed
  folder holding the Kuzu DB, and runs the build.

## Recipes

`execute-cypher`, `graph-features`, `graph-clustering`, `collect-nodes`:

- The graph **folder** is an input under a **named role** (e.g. `graph_db_folder`);
  the output goes under `main`.
- `Database type = Built-in`; the query lives in `customConfig.cypher_query`.
- Node properties keep their source column names.

## Graph Search agent tool

Type `Custom_agent_tool_<plugin>_graph-search`. Config keys: `llm_id`,
`db_folder_id` (the published graph folder), `database_type` (`"Built-in"`),
`db_query_timeout_seconds`. "Description for LLM" is a separate field, not a
config key. Attach to a Simple Visual Agent like any other tool.
