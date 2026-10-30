---
name: api-deployer
description: Deploy already published API service versions, select a single target version and verify asynchronous API deployment updates.
---

# API Deployer

Read [the shared Deployer guide](./deployer.md) first for instance selection,
coverage and recovery. Pass arguments through the shared read/write dispatcher. All operations below use `deployer_type="api"`.

API services are authored in a Design/Automation project's API Designer and
published as versioned packages. API Deployer manages those packages and sends them
to an infrastructure. An API node serves requests; it is not the Deployer profile.
The tool does not configure or invoke prediction endpoints.

1. Discover infrastructures and stages, then inspect the chosen target and its
   reported deployment permissions and governance policy. Infrastructure type
   determines available deployment behavior.
2. Discover published services and inspect the chosen source_id to identify its
   package versions. Do not confuse a saved-model version with an API package version.
3. Inspect existing deployment configuration, traffic mapping, health and history.
4. Create configuration with deployment_id, source_id (published service ID),
   infra_id and version. endpoint_id is optional for Deploy Anywhere infrastructures
   that deploy a particular endpoint; use a known endpoint from the package/UI.
   deployed_project_key and project_folder_id are project-only and rejected here.
5. Use `deployer.update_deployment(version=...)` to select one service version.
   This replaces any existing multi-version traffic mapping with SINGLE_GENERATION.
   Check the existing mapping and ensure a single-version transition matches intent.
   An older published version can be selected for rollback.
6. Use `deployer.update_deployment(enabled=false)` to save a disabled target, or
   enabled=true to save re-enablement. A save alone does not change serving state.
   Authentication and other settings are preserved.
7. Apply with `deployer.start_update`, track the future and exact update record, and
   re-read deployment health. A successful update does not prove prediction quality;
   endpoint invocation and test queries are outside this surface.

API service authoring/publication, advanced traffic splits, endpoint authentication,
API key handling, infrastructure provisioning and deployment deletion are not
exposed. Inspect the Dataiku UI for these operations and detailed error logs.
Never return raw light status: it can contain service and inherited API keys.

[Official Python API reference](https://developer.dataiku.com/latest/api-reference/python/api-deployer.html)
