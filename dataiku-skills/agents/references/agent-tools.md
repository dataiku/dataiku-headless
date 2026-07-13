# Agent Tools

Agent tools are project-level Dataiku objects that agents call during execution. They are distinct from MCP tools and are referenced by ID in a simple agent's `tool_ids` or a structured block's tool configuration.

## Built-in Tool Types

| Type | Use when |
| --- | --- |
| `DatasetRowLookup` | Looking up dataset rows by key. |
| `DatasetRowAppend` | Appending dataset rows. |
| `VectorStoreSearch` | Searching a knowledge bank or vector store. |
| `LLMMeshLLMQuery` | Querying an LLM or another agent as a subtask. |
| `ClassicalPredictionModelPredict` | Running a deployed prediction model for one record. |
| `GRELCalculator` | Evaluating GREL calculations. |
| `InlinePython` | Running custom inline Python logic. |
| `RemoteMCPClient` | Calling tools from a remote MCP server. |
| `DataikuReporter` | Sending a message through an integration. |
| `ApiEndpoint` | Calling a Dataiku API endpoint. |

Additional tool types can be added through plugins or pre-configured connections. Examples include SQL Question Answering, Semantic Model Query, Google Search, Jira, Salesforce, ServiceNow, Snowflake Cortex, and Databricks Genie. Custom plugin tools use a `Custom_agent_tool_<plugin>_<tool>` type name. Inspect available tools rather than assuming a plugin or connection exists.

## Interpretation Notes

- `additionalDescriptionForLLM` is the primary signal for tool selection. It should name the tool's purpose, appropriate inputs, and intended situations.
- Tool IDs are stable; display names are not. Agent configurations reference IDs.
- A `DatasetRowLookup` result exposes returned columns directly, rather than under a `rows` key.
- `LLMMeshLLMQuery` returns a plain response string; `ClassicalPredictionModelPredict` returns a prediction and probability values.

## Design Guidance

Use `requireHumanApproval: true` for consequential external actions, such as messaging or modifying production data. These tools cannot run inside `FOR_EACH` or `PARALLEL` blocks.

When inspecting a tool, compare its description and configuration with how the agent calls it. Vague descriptions, overly broad dataset access, and missing approval requirements are common sources of unsafe or unreliable behavior.
