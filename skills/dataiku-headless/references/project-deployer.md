---
name: project-deployer
description: Deploy already published project bundles to Automation infrastructures and verify the resulting project deployment.
---

# Project Deployer

Read [the shared Deployer guide](./deployer.md) first for instance selection,
coverage and recovery. Pass arguments through the shared read/write dispatcher. All operations below use `deployer_type="project"`.

A published project on Deployer is a collection of immutable bundle versions, not
a Design-node project that Cobuild can edit. A deployment associates a published
project and bundle with an Automation infrastructure and target project key.
Stages are infrastructure metadata, not configured instance types.

1. Discover infrastructures and stages. Inspect the intended infrastructure,
   associated deployments, governance policy and reported permissions.
2. Discover published projects and inspect the selected source_id to identify its
   package IDs. Do not infer a bundle ID from a Design project name or version.
3. For an existing deployment, inspect its saved settings, health and update history.
4. Create configuration with deployment_id, source_id (published project key),
   infra_id and version (bundle ID). Optional deployed_project_key and
   project_folder_id select the Automation target key and folder. Without these,
   Dataiku uses the published project key and root folder. Discover any folder ID
   on the target Automation instance; switch back to Deployer before creating.
   Never choose an existing target project key without understanding the overwrite
   effects of applying the bundle.
5. To promote or roll back an existing deployment, save a discovered bundle ID using
   `deployer.update_deployment(version=...)`. This preserves other deployment settings.
   The enabled argument and endpoint_id are API-only and rejected here.
6. Run `deployer.start_update` to apply the saved bundle. This may replace the
   Automation project's assets. Follow the future and exact update record, then
   re-read deployment health as described in the shared guide.
7. When project/output validation is needed, switch to the configured Automation
   instance, discover the actual deployed project and inspect it with the project,
   dataset and scenario guides. Deployer success does not establish output parity.

Bundle creation/publication, deployment remapping, code-environment behavior,
scenario activation and deployment tests are outside this tool surface. They
must already be configured in Dataiku. Do not use an arbitrary settings patch
or Cobuild on the Deployer to emulate those operations.

[Official Python API reference](https://developer.dataiku.com/latest/api-reference/python/project-deployer.html)
