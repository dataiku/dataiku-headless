# Tool surface decisions

## Short version

Keep one fixed MCP catalog, but remove a narrow reader only when another tool
returns the same evidence or a strict superset. Keep discovery, runtime state,
search, and verification tools because settings cannot replace them.

This rule removes 16 duplicate readers. It also retains 25 tools that the
original PR #4 allow-list removed even though they expose distinct evidence.
The resulting contract has 79 non-Cobuild tools and 5 Cobuild tools before
transport gating. Tests pin every name.

## Why this is worth doing

Agents choose tools more reliably when overlapping calls have a clear boundary.
They also need an independent read path: asking Cobuild what it built is not the
same as checking DSS. The useful target is therefore a small *non-overlapping*
surface, not the smallest possible count.

The rule follows Anthropic's guidance to consolidate narrow, related tools into
parameterized tools, while keeping distinct actions distinct. GitHub's MCP
server reached the same broad conclusion when it reduced its default tool set.
The MCP specification also treats the advertised tool list and each input schema
as the server's discoverable contract, so this repository tests the whole list.

## Removed readers and their replacements

The generic inspector uses the same `dataikuapi` accessor as each removed
settings reader. `tests/test_object_settings.py` exercises every dispatch path,
version lookup, invalid identifier, secret-redaction case, and final byte limit.

| Removed tool | Replacement | Why the replacement is equivalent |
|---|---|---|
| `get_agent_review` | `get_object_settings(object_type="agent_review")` | Returns the review's raw record, a superset of the old selected fields. |
| `get_agent_settings` | `get_object_settings(object_type="agent")` | Returns the same raw agent settings. |
| `list_agent_versions` | `get_object_settings(object_type="agent")` | Omitting `version_id` returns the settings and version inventory; passing it selects one version. |
| `get_agent_tool_settings` | `get_object_settings(object_type="agent_tool")` | Calls the same settings accessor and returns the same raw record. |
| `get_dashboard_settings` | `get_object_settings(object_type="dashboard")` | Calls the same settings accessor and returns the same raw record. |
| `get_dataset_column_descriptions` | `get_dataset_info(columns=[...])` | Keeps caller-ordered column selection and comments, and adds type, meaning, connection, counts, and truncation state. |
| `get_evaluation_store_details` | `get_object_settings(object_type="evaluation_store")` | Returns store settings and evaluation details with per-evaluation failure isolation. |
| `get_insight_settings` | `get_object_settings(object_type="insight")` | Calls the same settings accessor and returns the same raw record. |
| `get_knowledge_bank_settings` | `get_object_settings(object_type="knowledge_bank")` | Calls the same settings accessor and returns the same raw record. |
| `get_ml_analysis_settings` | `get_object_settings(object_type="ml_analysis")` | Returns the analysis name, input dataset, task id, and task settings. |
| `get_retrieval_augmented_llm_settings` | `get_object_settings(object_type="retrieval_augmented_llm")` | Calls the same settings accessor and returns the same raw record. |
| `list_saved_model_versions` | `get_object_settings(object_type="saved_model")` | Omitting `version_id` returns the model's version inventory. |
| `get_saved_model_version_details` | `get_object_settings(object_type="saved_model", version_id=...)` | Returns the selected version detail snippet and its detail class. |
| `get_semantic_model_version_settings` | `get_object_settings(object_type="semantic_model", version_id=...)` | Returns the selected version's raw settings; omitting the version returns version discovery. |
| `get_webapp_settings` | `get_object_settings(object_type="webapp")` | Calls the same settings accessor and returns the same raw record. |
| `get_wiki_article` | `get_object_settings(object_type="wiki_article")` | Returns the same article name and body. |

`tests/test_tool_pruning.py` separately proves the dataset-column replacement,
including named selection. The generic result is recursively secret-redacted and
has a hard 1 MB serialized ceiling. Dataset schema output has both an explicit
column limit and a hard 1 MB final serialized ceiling.

## Tools retained after reviewing the original pruning

The original surface commit removed the tools below. None is equivalent to a
settings dump, so this split keeps each one.

| Capability | Retained tools | Why settings cannot replace them |
|---|---|---|
| Find object identifiers | `list_agent_reviews`, `list_agent_tools`, `list_dashboards`, `list_evaluation_stores`, `list_insights`, `list_knowledge_banks`, `list_retrieval_augmented_llms`, `list_semantic_models`, `list_webapps`, `list_wiki_articles` | The generic inspector needs an object id. These calls discover valid ids and basic metadata. |
| Agent-review evidence | `list_agent_review_tests`, `list_agent_review_runs`, `get_agent_review_run_results` | Tests, executions, pass/fail results, and trait outcomes are runtime evidence, not configuration. |
| Web-app evidence | `get_webapp_state` | Live backend state is not present in WebApp settings. |
| Data-quality evidence | `get_data_quality_rule`, `get_data_quality_rule_history`, `get_data_quality_rule_results` | Rule definition, history, and result detail answer different verification questions than the aggregate status tool. |
| LLM and knowledge evidence | `get_llm_info`, `search_knowledge_bank` | Provider/model detail and retrieval results are not object settings. |
| ML evidence | `get_ml_analysis_summary`, `list_ml_analysis_models`, `get_ml_model_details` | Trained model discovery, metrics, and detail are runtime artifacts. |
| Scenario prerequisites | `list_messaging_channels` | `run_scenario` may need a channel id; scenario settings do not provide the instance-wide inventory. |
| Project-library work | `search_project_library`, `validate_project_library_file` | Search and syntax validation are distinct operations, not settings reads. |

This corrects the main inspection concern in the first PR #4 review: Cobuild no
longer has to grade its own work for these object families.

## Project-library safety boundary

Retaining library search and validation is useful only if they cannot turn into
unbounded work. These tools therefore expose separate limits for returned items,
all visited nodes, tree depth, files read, bytes accepted per file, matches, and
validation size. Every partial result says `truncated: true` and lists its
reasons. A separate 1 MB final serialized ceiling covers unusually long paths,
metadata, matches, and syntax details that count limits alone cannot bound.

The visited-node counter includes entries excluded by a source filter. This
fixes a defect in the original PR #4 implementation, which capped matching rows
but could still traverse an unlimited number of non-matching nodes. Traversal is
iterative, so a deeply nested tree cannot exhaust Python's call stack.

Regex search uses the maintained `regex` package because its matching API has a
real timeout. A per-match timeout prevents hostile patterns from consuming a
worker indefinitely. A cooperative time budget stops traversal and matching
between synchronous SDK calls; the Dataiku client's own HTTP timeout still
governs an in-flight DSS request. Reads accept UTF-8 text only,
clip on code-point boundaries, and report full and returned byte counts. Python
validation rejects oversized input instead of parsing a clipped file.

The DSS project-library SDK returns a whole file rather than a ranged stream.
The server can therefore bound parsing and output after the SDK call, but it
cannot stop DSS from transferring that one response. The code states this limit
through a hard accepted-file ceiling instead of claiming an upstream range that
the SDK does not support.

## Provenance and evidence

- [PR #4](https://github.com/dataiku/dku-headless/pull/4) introduced the fixed
  supervisor surface. Its pruning commit was
  [`c753f9b`](https://github.com/dataiku/dku-headless/commit/c753f9b75e32bf59521b8e46c5df23e2c7d9f04d).
- The generic inspector came from PR #4 commits
  [`9edf6fd`](https://github.com/dataiku/dku-headless/commit/9edf6fd2) and
  [`610787a`](https://github.com/dataiku/dku-headless/commit/610787a7). This
  sub-PR keeps that consolidation but tests the equivalence boundary before
  deleting anything.
- The [first review](https://github.com/dataiku/dku-headless/pull/4#pullrequestreview-4737994324)
  challenged the lost independent inspection paths. The later
  [scope comment](https://github.com/dataiku/dku-headless/pull/4#issuecomment-5028205473)
  asked for changes that reviewers can assess separately. This document records
  each decision for that purpose.
- [Anthropic's tool guidance](https://www.anthropic.com/engineering/writing-tools-for-agents)
  recommends consolidating overlapping narrow tools and designing around agent
  context. [GitHub's MCP discussion](https://github.com/github/github-mcp-server/discussions/1182)
  describes a comparable default-surface reduction.
- The [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
  defines tool discovery and input schemas as the protocol contract.
- Dataiku's [project API](https://developer.dataiku.com/latest/api-reference/python/projects.html)
  and [dataset API](https://developer.dataiku.com/latest/api-reference/python/datasets.html)
  document the underlying project and schema reads. The locked
  `dataiku-api-client` source was also checked at commit
  [`137e7669`](https://github.com/dataiku/dataiku-api-client/commit/137e7669a5423166040319dff11dc5f94f6ccbbe).
- The `regex` project's [timeout documentation](https://github.com/mrabarnett/mrab-regex#timeout)
  states that a timeout covers the whole match operation.

This slice is not a port from `dku-cli`. Its source is the named PR #4 commits,
the reviewer comments, the current Dataiku SDK, and the external tool-design
evidence above. The later skill-architecture slices identify their separate
`dku-cli` provenance.
