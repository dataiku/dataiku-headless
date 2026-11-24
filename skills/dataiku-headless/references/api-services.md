---
name: api-services
description: Create, inspect, update and publish API Services on Design. Use for endpoint authoring, version creation, publication and verification before deployment.
---

# API Services

An API Service groups endpoints that are versioned and deployed together. A package
is a snapshot of the service and its required artifacts. Publication sends that
version to the Design node's configured API Deployer; deployment activates it on
API Nodes or other configured serving infrastructure.

These tools require a `design` profile. API Service authoring and publication are
narrow direct-write exceptions to Cobuild routing. Use Cobuild to build or change
the underlying Flow, models and other analytic assets.

## Workflow for Creating or Updating API Services

1. **Orient:** Select the intended Design instance and project. Use `list_projects`
   or `list_api_services(project_key)` when the target is unclear; inspect a named
   target directly.
2. **Open or create the service:**
   - **Existing service:** Call `get_api_service(project_key, service_id)` to read
     its name, authentication mode, endpoint definitions and package versions.
   - **New service:** Choose a descriptive unused ID within the user's request and
     call `create_api_service(project_key, service_id)`. This creates an empty
     service and returns a receipt. Call `get_api_service` to read its initial name
     and authentication mode before configuring it.
3. **Configure endpoints:** For both new and existing services, choose the endpoint
   family from the catalog below and read its section in
   [API Endpoint Definitions](./api-services/api-endpoint-definitions.md). Discover
   the required models, datasets, folders, connections and code environments. Build
   complete definitions for the endpoints being added or changed, including `id`,
   `type` and the family's required fields. When editing an existing endpoint,
   start from its inspected definition and preserve options outside the requested
   change. For a display-name-only change, skip endpoint configuration.
4. **Save:** Call `update_api_service(project_key, service_id, name=...,
   endpoints=[...])` for either a new or existing service. Supply only the requested
   name change and affected endpoints. New endpoint IDs are added; matching IDs
   replace their **complete definitions**. Omitted IDs stay unchanged unless listed
   in `remove_endpoint_ids` (see endpoint deletion below). Omit `endpoints` for a
   name-only update. Never submit redaction placeholders; report
   the coverage gap if hidden values prevent a safe replacement.
5. **Validate:** Re-read with `get_api_service` and compare the saved name and
   endpoints with the request. Check references and runtime prerequisites using
   the endpoint guide. Saving does not execute endpoints or update existing
   packages/deployments. Use the Dataiku UI for Design development-server tests,
   and report inspection separately from passed execution tests.

When publication is requested, continue below. For tests of an already deployed
API Service version, use [API Deployer](./api-deployer.md#test-deployed-endpoints).

## Workflow for Publishing API Services

1. **Select the version:** Use `get_api_service` to inspect the service and existing
   package IDs. If the user asks to publish the current service, create a new
   package and then publish it as one workflow. If they name an existing version,
   publish that package directly; do not rebuild it from the current definition.
2. **Create a version when needed:** Confirm the intended endpoints, dependencies
   and authentication, then call `create_api_service_package(project_key,
   service_id, package_id, release_notes=...)`. Release notes belong to package
   creation. Packaging captures active saved-model versions, folder files and
   bundled lookup data; later changes require a new package. Existing IDs fail.
   Allow the request to finish, then verify the package appears in `get_api_service`.
3. **Publish:** Call `publish_api_service_package(project_key, service_id,
   package_id, published_service_id=...)`. Omit `published_service_id` to use the
   source service ID. This target identifies a published service, not a deployment
   or infrastructure. A missing published service is created on the configured
   API Deployer. The selected local profile does not override that destination.
4. **Verify publication:** Select the actual destination's `deployer` profile.
   Describe `deployer.get_published_item`, then call `run_read_operation` with
   `operation_id="deployer.get_published_item"`,
   `arguments={"deployer_type": "api", "source_id": "<published service ID>"}`,
   and `expected_instance` set to the selected Deployer instance name. Confirm the
   returned package `id` matches `package_id`. If the configured destination is
   unknown, establish it from the Design node's Deployer settings/UI or the user;
   do not assume that an arbitrary saved Deployer profile is the destination.
5. **Deploy and test when requested:** Follow [API Deployer](./api-deployer.md) to
   create/update a deployment, apply it, inspect health and run endpoint tests.
   Publication alone does not create a deployment or change live traffic. Keep
   saved-model version, API package version and deployment ID distinct.

## Workflow for Deleting Endpoints

1. **Inspect:** Call `get_api_service(project_key, service_id)` and identify the
   exact endpoint IDs to remove and the sibling endpoints to preserve.
2. **Remove:** Call `update_api_service(project_key, service_id,
   remove_endpoint_ids=["<endpoint ID>"])`. This removes only the listed endpoints
   using the public SDK's settings save; other endpoints and service settings are
   preserved. Do not pass the remaining endpoints back as a replacement list.
3. **Verify:** Re-read with `get_api_service`. Confirm the selected endpoints are
   absent and sibling definitions are unchanged. If the save outcome is uncertain,
   inspect before retrying. A removal request containing an unknown ID fails
   without saving changes.

Omitting an endpoint from `endpoints` or sending `endpoints=[]` does not delete it.
Use `remove_endpoint_ids` explicitly. Removal can be combined with a name change
or additions/replacements, but the same endpoint ID cannot be both removed and
replaced in one call. All requested changes are saved together.

Removal changes the editable service only. Existing packages and serving
deployments retain their snapshot. When removal from a deployment is requested,
create and publish a new version, then follow [API Deployer](./api-deployer.md) to
apply it and verify the serving state.

## Action Semantics

| Input or action | Behavior |
| --- | --- |
| `project_key`, `service_id` | Required on every tool except `list_api_services`, which needs only `project_key`. Discover existing IDs; choose new IDs within the user's request. |
| New service/endpoint IDs | Use letters, digits, underscores or hyphens. `name` changes only the service's display name, not its ID. |
| `update_api_service(name=...)` | Non-empty display name. Omitted name stays unchanged. |
| `update_api_service(endpoints=[...])` | Complete definitions: new IDs add; matching IDs replace; omitted IDs stay unchanged. `[]` does not clear endpoints. No partial field patch; use `remove_endpoint_ids` for deletion. |
| `update_api_service(remove_endpoint_ids=[...])` | Removes the listed existing endpoints. IDs must be unique and must not overlap supplied endpoint definitions. An unknown ID prevents the save. `[]` removes nothing. |
| Empty update | Supply a name, at least one endpoint definition, or at least one ID to remove. Omit optional arguments to leave them alone; `null` is not a delete instruction. |
| `create_api_service_package` | Creates a new snapshot. `package_id` may also contain dots but cannot start with a dot. Optional `release_notes` describes this version's changes. |
| `publish_api_service_package` | Publishes an existing package with its embedded notes. `published_service_id` defaults to `service_id`; it does not select a Deployer instance. |

Reads require project READ_CONF. Authoring and packaging require WRITE_CONF and
access to the referenced data/artifacts. Publication requires WRITE on the existing
published service, or the Deployer's global Create published API services permission
when creating one.

## Endpoint Family Catalog

Read the relevant section before creating or replacing an endpoint. Listing
services or publishing an existing package does not require the child reference.

| Use when | Endpoint types | Definition reference |
| --- | --- | --- |
| Serve a visual or imported MLflow model | `STD_PREDICTION`, `STD_CLUSTERING`, `STD_FORECAST`, `STD_CAUSAL_PREDICTION`, `STD_MULTITARGET_PREDICTION` | [Model endpoints](./api-services/api-endpoint-definitions.md#visual-models) |
| Run application code | `PY_FUNCTION`, `R_FUNCTION` | [Functions](./api-services/api-endpoint-definitions.md#python-and-r-functions) |
| Serve a custom predictor | `CUSTOM_PREDICTION`, `CUSTOM_R_PREDICTION` | [Custom prediction](./api-services/api-endpoint-definitions.md#python-and-r-custom-prediction) |
| Retrieve dataset values | `DATASETS_LOOKUP` | [Dataset lookup](./api-services/api-endpoint-definitions.md#dataset-lookup) |
| Execute parameterized SQL | `SQL_QUERY` | [SQL query](./api-services/api-endpoint-definitions.md#sql-query) |

## Authentication and Recovery

- `get_api_service` returns `auth_method`: `PUBLIC` (no authentication), `API_KEYS`,
  or `OAUTH2`. These tools preserve authentication, credentials, monitoring and other
  service settings. If authentication needs changing, use the service's Security
  settings in the Dataiku UI, then re-read and create a new package. The reported
  mode does not prove that credentials/OAuth are functional. Do not reuse the
  Headless instance credential as an endpoint credential.
- Reads omit service credentials and raw package diagnostics, redact nested endpoint
  credential fields, preserve saved header names, and redact all saved header values.
  Other result redaction is best effort by field name. Code, SQL and test queries can
  contain application data; use only what the task needs and never embed credentials
  in examples.
- After a timeout, cancellation or uncertain result, inspect on the same instance
  before retrying. Creation may have completed; settings may be saved; packaging
  may still be running. Check the configured API Deployer's versions after an
  uncertain publication. Retry publication of an existing package rather than
  choosing a new package ID merely to bypass uncertainty.

Authentication changes, API key handling, package downloads and Design
development-server execution also remain Dataiku UI tasks.
Report a coverage gap rather than bypassing the tools with SDK scripts or internal APIs.

## Official References

- [API Node concepts](https://doc.dataiku.com/dss/latest/apinode/concepts.html)
- [Knowledge Base: endpoint types](https://knowledge.dataiku.com/latest/deploy/api-deployment/concept-api-endpoints.html)
- [Knowledge Base: query enrichments and data deployment](https://knowledge.dataiku.com/latest/deploy/api-deployment/concept-query-enrichments.html)
