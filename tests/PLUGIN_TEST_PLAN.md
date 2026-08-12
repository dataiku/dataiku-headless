# Headless plugin capability test plan

## Objectives

Verify that plugin development is safe, component-aware, compatible with the
supported DSS API, and usable end to end from local source through installation.

## Test layers

| Layer | Coverage | Execution |
| --- | --- | --- |
| Unit | Local filesystem, manifest/component validation, conversion shaping, archive safety, overwrite/path guards | Every change, no DSS access |
| Mocked DSS | Plugin metadata, settings, files, usages, futures, code environments, Store/Git dispatch, install/update/delete | Every change, fake client |
| Live read-only | Recipe/WebApp inspection and local conversion from existing DSS assets | On plugin/conversion changes |
| Live disposable lifecycle | Install, inspect, update, usage check, delete, final absence check | On deployment/lifecycle changes |

## Required scenarios

### Local source and packaging

- Scaffold with every supported component directory.
- Reject invalid IDs, invalid manifests, missing descriptors, and missing implementation files.
- Validate recipe, connector, webapp, agent, guardrail, block, step, format, provider, probe, check, trigger, runnable, and parameter-set layouts.
- Package with `plugin.json` at ZIP root.
- Exclude VCS, virtualenv, cache, and OS metadata files.
- Reject path traversal and unsafe local file operations.
- Enforce overwrite guards.

### DSS lifecycle

- List and inspect installed plugins with secret masking.
- Read/write/rename/move development-plugin files.
- Download installed plugins.
- Install and update from local ZIP/directory.
- Install/update from Plugin Store and Git.
- Create, assign, and rebuild plugin code environments.
- Check usages before deletion; require force for in-use plugins.
- Handle asynchronous DSS futures.

### Conversion

- Convert Python recipes with dataset roles, multiple roles, parameters, and hard-coded reference warnings.
- Reject non-Python recipes.
- Convert Standard, DASH, Bokeh, Streamlit, and Shiny WebApps according to their DSS settings shape.
- Validate and package converted output.
- Preserve source DSS assets without mutation.

### Live acceptance

- Use existing project assets for read-only conversion.
- Use a uniquely named disposable plugin for install/update/delete.
- Confirm the disposable plugin is absent after cleanup.

## Acceptance criteria

- All unit and mocked-DSS scenarios pass.
- Live conversion output validates and packages successfully.
- Disposable lifecycle completes and leaves no test plugin installed.
- No project asset is changed by conversion tests.
- No credentials appear in test output or tool responses.
