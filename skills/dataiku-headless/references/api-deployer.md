---
name: api-deployer
description: Deploy published API Services, verify asynchronous updates, and run endpoint test queries on deployed versions.
---

# API Deployer

Read [the shared Deployer guide](./deployer.md) first for instance selection,
coverage and recovery. Pass arguments through the shared read/write dispatcher. All operations below use `deployer_type="api"`.

API services are authored in a Design/Automation project's API Designer and
published as versioned packages. API Deployer manages those packages and sends them
to an infrastructure. An API node serves requests; it is not the Deployer profile.
Test deployed endpoints with `deployer.run_test_queries`.

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
   re-read deployment health. A successful update does not establish readiness:
   Kubernetes rollout or public-address provisioning may still be in progress.
   Inspect health messages and wait for readiness before testing; keep tracking the
   existing update rather than resubmitting it. A healthy deployment does not prove prediction quality;
   run representative endpoint test queries when execution validation is requested.

## Test deployed endpoints

Use `deployer.run_test_queries` through `run_write_operation`, even for prediction
or lookup endpoints: function/SQL endpoints may write data or trigger external
work. This runs real requests against the currently serving deployment; it is not
a dry run or a Design development-server test. No publication or deployment update
is performed by the test operation.

1. Select the intended `deployer` profile. Use `deployer.get_deployment` to inspect
   health, configured versions/traffic mapping, and `endpoints` (IDs, types and saved
   `test_queries`). An unhealthy or out-of-sync deployment is not proof that the
   corresponding current Design definition is invalid. Do not repair or redeploy it
   merely to get a test result unless that is part of the user's request.
2. Choose one endpoint explicitly. For function and SQL endpoints, inspect the
   corresponding code/query and side effects before execution. Check the deployed
   package and origin; current Design code may have changed since packaging.
3. Omit `test_queries` to execute all saved queries from the deployed package for
   that endpoint. Inspect them first. An empty saved list executes no tests and is
   not a pass. To bound a test or supply missing queries, provide 1–20 objects with
   required `q` (the request body), optional `name`, and optional
   `headers: [{"key": "X-Example", "value": "example"}]`. Use only non-sensitive
   explicit bodies and header values: the pinned SDK places supplied bodies and
   headers in the request URL, which DSS or proxy access logs may retain. Custom
   headers depend on the server version; older servers may silently ignore them.
   When credentials are needed, prefer a saved query on a server that supports its
   headers. Bodies follow the endpoint family's contract in
   [API Endpoint Definitions](./api-services/api-endpoint-definitions.md#test-queries).
   Explicit queries execute without being saved into the service or package.
4. Describe the operation, then execute this shape:

   ```json
   {
     "operation_id": "deployer.run_test_queries",
     "expected_instance": "<selected Deployer instance name>",
     "arguments": {
       "deployer_type": "api",
       "deployment_id": "<discovered deployment ID>",
       "endpoint_id": "<discovered endpoint ID>",
       "test_queries": [{"q": {"features": {"<feature name>": 1}}}]
     }
   }
   ```

   This example is for an API Node prediction endpoint; use the selected endpoint's
   actual feature names, data types and non-sensitive representative values. Managed
   deployments can require a different body shape (for example, Vertex AI uses
   `instances`). A saved query from the target deployment is a good starting point.
   Do not send redacted placeholders.
5. Repeat for each endpoint to validate the whole API Service. A passing test on
   one endpoint does not validate its siblings. Inspect `query_count`, `succeeded_count`, `failed_count`,
   `all_requests_succeeded`, `uncertain_count`, and each `responses` entry
   (`query_index`, `request_succeeded`, `outcome_uncertain`, and `response` or error
   type/code). A timeout or transport error can leave endpoint effects uncertain;
   inspect effects before retrying. Zero queries never count
   as a pass. These flags report request execution, not prediction quality or
   application correctness: inspect response records for errors and compare outputs
   with expected behavior. For multi-version routing, one successful request does
   not establish that every version works; retain the configured mapping and any
   version reported in the response.

Responses have credential fields redacted by best effort field-name matching and
omit query echoes, response headers, raw error messages and stack traces. Large
individual response bodies are bounded and marked with `response_truncated`; SQL
rows may carry values positionally, so field-name redaction cannot detect every
sensitive value. Inspect detailed failures in the Deployer test
UI. After a timeout or uncertain failure, queries may already have executed; do not
blindly retry functions or SQL with side effects. Test requests can create audit
records and incur normal serving costs.

For Design service authoring and package publication, use [API Services](./api-services.md).

Advanced traffic splits, endpoint authentication,
API key handling, infrastructure provisioning and deployment deletion are not
exposed. Use the Dataiku UI for these operations; inspect deployment failures with
`deployer.get_update`, adding `include_logs=true` when needed.
Never return raw light status: it can contain service and inherited API keys.

[Official Python API reference](https://developer.dataiku.com/latest/api-reference/python/api-deployer.html)
