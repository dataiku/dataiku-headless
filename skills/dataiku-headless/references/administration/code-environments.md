---
name: code-environments
description: Discover and administer Dataiku code environments, or select one for a recipe, ML analysis, or code agent.
---

# Code Environments

Use this guide to inspect code environments and administer them when the user explicitly requests instance-level code-environment work. Code environment administration is a direct-write exception: it is not an in-project asset and Cobuild does not manage it.

## Code Environment Concepts

A code environment provides the language runtime and installed dependencies for code-based work, including Python, R, and PySpark recipes, ML analyses, and code agents.

An asset can use an explicitly selected environment, inherit a configured default, or use its language's built-in environment. Choose an explicit environment only when the user requests it or the task/error context establishes that it is needed.

Matching a workload's language does not establish package or runtime compatibility. Diagnose failures using error details and known requirements, and involve Cobuild or an administrator when the available context is insufficient.

## Workflow

1. Use `list_code_envs` with its default partial search to discover environments. To find environments declaring dependencies, pass `packages` as a list of package names, for example `packages=["pandas", "numpy"]`; every returned environment declares every listed package.
2. Use `search_mode="exact"` with `include_details=true` to inspect one exact environment before updating it. Details include owner, group access, requested packages, installed packages, and build targets.
3. Before setting an owner or group permissions, obtain the exact Dataiku login and group names using `./users.md` and `./groups.md`.
4. Before setting container execution or Spark Kubernetes targets, obtain configuration names according to `./general-settings.md`; do not invent names.
5. Create only managed Design-node `PYTHON` or `R` environments. Package-spec changes are also limited to managed Design-node environments; permissions, build targets, and rebuilds can be updated on other environment types.
6. Requested-package changes automatically update the local environment and rebuild images. Container or Spark Kubernetes target changes rebuild images. Use `force_rebuild=true` only when a clean local environment rebuild is intended; it does not rebuild images by itself.
7. Use `delete_code_env` when deletion is requested. It checks Dataiku usages first and returns any blocking PROJECT, NOTEBOOK, SCENARIO_STEP, or other usage records with remediation guidance; do not infer that deletion succeeded until `deleted` is true.
8. Route recipe, ML analysis, and code-agent environment selection changes through `../cobuild.md`.

## Permissions

- Detailed reads, creation, and updates require the global **Create code envs** or **Manage all code envs** permission.
- Deletion requires the global **Manage all code envs** permission.
- Per-environment update and deletion permissions apply only in the Dataiku UI. They do not authorize MCP-based updates or deletion.
- Dataiku permission and validation errors are returned directly. Do not infer permission from a failed package install or select an alternative environment without grounded compatibility evidence.

## Supported Settings

- Python package entries are requirements-style lines. R entries use Dataiku raw package-spec lines, for example `"RJSONIO","1.3"`.
- Package filtering matches declared/requested package names, not transitive packages installed while resolving those declarations. It accepts names only; inspect `requested_packages` for a version or compatibility question.
- Package-spec changes are supported only for `DESIGN_MANAGED` environments. Non-`DESIGN_MANAGED` deployment modes are `DSS_INTERNAL`, `PLUGIN_MANAGED`, `PLUGIN_NONMANAGED`, `BUSINESS_APP_MANAGED`, `DESIGN_NON_MANAGED`, and `EXTERNAL_CONDA_NAMED`.
- Owner, `usable_by_all`, and group permissions are supported. Supplying group permissions replaces the full group permission list. A group permission item has the form `{"group": "data-science", "use": true, "update": false, "manage_users": false}`.
- Container execution and Spark Kubernetes build targets are supported. Supplying any target during creation builds the resulting images; target changes rebuild images automatically on update.
- `all_container_configurations` and `all_spark_kubernetes_configurations` take precedence over any listed configurations; listed values are preserved but ignored by Dataiku while their corresponding `all_*` value is true.
- Resources, Conda/custom repositories, base-package choices, Automation/API-node, and versioned environments are out of scope.

## Preferred Tools

- `list_code_envs`
- `create_code_env`
- `update_code_env`
- `delete_code_env`

## Safety Rules

- Do not select an explicit environment solely from a package or import error unless its compatibility is otherwise established.
- Do not retry a blocked deletion until every returned usage has been removed or moved to another environment.
