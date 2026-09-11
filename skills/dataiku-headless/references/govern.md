---
name: govern
description: Operate Dataiku Govern through its public Python API, with task-specific guidance for artifacts, blueprints, signoffs, and administration.
---

# Govern

Govern runs on a separate node. Its records are artifacts described by blueprint
versions, with workflow steps and signoffs. A governed project is an artifact;
it is not a DSS project containing datasets and recipes.

Use the public `dataikuapi.GovernClient` API through local Python execution for
Govern reads and writes. This is a documented exception to Headless's MCP-only
workflow. DSS project work still uses MCP and Cobuild. No Govern MCP tools or DKU
CLI installation are required.

## Connect

The agent needs local Python execution, a compatible `dataiku-api-client`, and a
Govern URL and API key supplied securely to that execution environment. MCP server
credentials are not automatically available to local commands. Headless's current
setup and instance-switching tools configure DSS; do not repurpose them for Govern.

Use `DKU_GOVERN_URL` and `DKU_GOVERN_API_KEY` as this guide's environment-variable
convention. These are not new Headless configuration settings. Have the operator
supply missing credentials through their host's secret/environment configuration,
not in chat, scripts, or command-line arguments. Do not print credentials or dump
the environment. Keep certificate verification enabled.

Create a task script outside the plugin installation. If the execution environment
does not already provide the SDK, run it in an isolated environment, for example:

```bash
uv run --no-project --with 'dataiku-api-client==14.7.2' python /absolute/path/govern_task.py
```

The examples were checked against 14.7.2, Headless's current locked SDK. Use a client
version compatible with the target Govern release; the MCP runtime's dependencies
do not install the SDK into the agent's shell. Start the script with:

```python
import os
import dataikuapi

govern_url = os.environ["DKU_GOVERN_URL"].rstrip("/")
client = dataikuapi.GovernClient(
    govern_url, api_key=os.environ["DKU_GOVERN_API_KEY"]
)
info = client.get_instance_info()
if info.node_type != "GOVERN":
    raise RuntimeError("The selected URL is not a Govern node")
identity = client.get_auth_info()
print({"url": govern_url, "node_type": info.node_type,
       "identity": identity.get("authIdentifier")})
```

Check that the target and identity match the task. Keep the server version from
instance information when available; the SDK package version is not the server
version. Permissions depend on the operation: ordinary reads need access to the
objects, while blueprint design and administration require the corresponding rights.
If execution, credentials, or permissions are missing, report that specific blocker.

## Choose the task guide

| Task | Read next |
| --- | --- |
| Discover, create, or update governed records; inspect field schemas | [Artifacts](./govern/artifacts.md) |
| Design blueprint versions, fields, workflow, views, or hooks | [Blueprints](./govern/blueprints.md) |
| Configure review gates or work with feedback, approvals, and workflow state | [Signoffs](./govern/signoffs.md) |
| Manage roles, users, groups, pages, attachments, or time series | [Supporting objects](./govern/supporting-objects.md) |

## Execution pattern

Discover IDs, read the full target definition, change only the requested fields,
save, and fetch again to verify. SDK handles and successful saves do not prove that
the desired values persisted. Summarize relevant fields instead of dumping an estate.
For multi-step work, verify each completed unit and retain created IDs; after an
uncertain write, inspect before retrying a create or other non-idempotent operation.

Use the [official Govern API reference](https://developer.dataiku.com/latest/api-reference/python/govern.html)
and local `help()` / `inspect.signature()` for methods not shown here. Match the docs
to the target release. If the installed SDK lacks a public operation, report the gap;
do not call private `_perform_*` methods or invent REST endpoints. The DKU CLI is a
source of workflow patterns, not an execution dependency or a guarantee of SDK parity.
