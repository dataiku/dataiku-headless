---
name: deployer
description: Inspect and operate Project and API Deployer deployments, selecting the correct node and tracking asynchronous updates.
---

# Deployer

Deployer is an instance-level control plane with two independent components:
Project Deployer sends published project bundles to Automation nodes; API Deployer
sends published API service versions to API nodes or supported managed infrastructures.
Deployer may be standalone or enabled locally on a Design or Automation node.
All 13 operations, including future polling, use the schema-backed registry described in [Operations](./operations.md). Deployer operations require a profile declared as type `deployer`.
These deployment operations are direct instance-level exceptions to Cobuild routing.
Building the underlying Flow, models or API endpoint logic remains project work.

## Select the target first

1. Inspect `list_instances` and `get_current_instance`; select the intended Deployer
   using `switch_instance`. Keep its name and reported Dataiku version in context.
2. The configured `instance_type` is metadata. A profile marked deployer does not
   verify that Deployer is enabled or the credential has deployment privileges.
   For a local Deployer on a Design or Automation node, configure a separate
   `deployer` profile pointing at that URL. Design and Automation profiles cannot
   call the v2 operation tools. Tools address the selected node; they do not follow its remote Deployer configuration automatically.
3. Read [Project Deployer](./project-deployer.md) for bundles or
   [API Deployer](./api-deployer.md) for real-time services.
4. Supply `deployer_type="project"` or `deployer_type="api"` on every call. IDs
   belong to that component on that instance, even when names happen to match.

## Shared inspection and execution

- `deployer.list_stages` discovers configured stage IDs and descriptions.
- `deployer.list_infrastructures` returns target summaries. `deployer.get_infrastructure`
  adds saved settings with credential values redacted. Permissions are reported
  when supplied by Dataiku.
- `deployer.list_published_items` discovers projects/services.
  `deployer.get_published_item(source_id=...)` returns available packages as a
  columnar table with id, publishedOn and publishedBy. Use those IDs as versions.
- `deployer.list_deployments` reports configuration, not live health.
  `deployer.get_deployment` adds full saved settings with credential redaction,
  health and structured governance messages.
- `deployer.create_deployment` creates configuration only. Existing IDs fail through
  Dataiku; this tool has no overwrite mode.
- `deployer.update_deployment` saves only a target version and/or API enablement.
  Saving is not execution. Other settings are preserved; API version selection
  replaces the existing traffic mapping with a single-version mapping.
- `deployer.start_update` applies the saved settings asynchronously. It can replace
  production assets, alter API traffic, or disable an API deployment. Inspect the
  target and saved version first, and execute only within the user's request.

Keep `ignore_warnings=false` on the initial `deployer.create_deployment` or
`deployer.update_deployment` call. If governance rejects it, inspect the
infrastructure policy. For a warning, explain the warning, version and target to
the user and obtain explicit approval before retrying with `ignore_warnings=true`.
Approval applies only to that version and target; blocking governance policies
cannot be overridden with this parameter.

## Track the same update

Keep the selected instance, deployer_type, deployment_id and returned future_id.
Poll `deployer.get_future_status(future_id=...)` on that same instance. Do not use Flow job
IDs or assume a configuration save means an update completed. Then inspect
`deployer.list_updates`, pin the matching startTimestamp with
`deployer.get_update(timestamp=...)`, and re-read `deployer.get_deployment`.
Use the update's `report` to investigate failures. Add `include_logs=true` when
you need the available log lines for that update. Generated Kubernetes Deployment
and Secret manifests are replaced with redaction markers because they can contain
plaintext or base64-encoded environment secrets. Filtering resumes at the next
recognized Dataiku log-entry header; truncated entries or custom log formats may
cause the remaining lines to be omitted. This is not a general sanitizer for
arbitrary secrets printed by custom deployment hooks.
Omitting timestamp reads the latest update, which may belong to another caller.
Completion of a future alone does not establish a healthy deployed service/project.

If a request times out, is cancelled, returns no future ID, or fails after submission,
inspect deployment state and update history before retrying. Do not resubmit an
uncertain update. Reconnect to the same configured instance when resuming.

## Coverage limits

Lists and status summaries expose selected operational fields. Infrastructure and
deployment detail reads also return backend-defined `settings` with credential
values redacted.
Deployment detail includes health and governance explanations. Update detail
includes diagnostic reports and supports optional logs.

Create and publish project bundles on Design using the
[Project bundles guide](./project-bundles.md), then return here to deploy them.

There are no writes here for infrastructure provisioning, connection remapping,
authentication, permissions, advanced traffic mappings, deletion, local bundle
download/upload, API package publication, or deployment test execution. Deployer operations work with
already published packages.
Report missing coverage; do not bypass it with raw SDK or REST calls. Use Cobuild for supported
in-project asset construction; report publication gaps outside the documented
Design bundle tools.

## Official documentation

- [Production deployments and bundles](https://doc.dataiku.com/dss/latest/deployment/index.html)
- [API Node and API Deployer](https://doc.dataiku.com/dss/latest/apinode/introduction.html)
