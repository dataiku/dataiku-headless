---
name: general-settings
description: Inspect Dataiku container execution and Spark configurations from General Settings.
---

# General Settings

Use this guide to inspect instance-level container execution and Spark configurations. These tools require global administrator credentials and are read-only direct MCP tools.

## Workflow

1. Use `list_container_exec_configs` to discover container execution configuration names and their workload/access settings.
2. Use `list_spark_configs` to discover all named Spark configurations. Check `managed_kubernetes` before using one as a Spark Kubernetes code-environment image target.
3. Use `include_details=true` only when runtime resources, namespaces, image build configuration, Spark properties, or credential modes are needed.

## Permissions And Boundaries

- General Settings are available only to Dataiku administrators.
- If the caller lacks administrator access, do not attempt to infer configuration names or use these tools indirectly. Direct them to the Dataiku UI to inspect or change configuration selection, including for code-environment image targets and recipe execution.
- These tools expose configuration references and redacted operational details; they do not create, update, or delete General Settings.

## Preferred Tools

- `list_container_exec_configs`
- `list_spark_configs`
