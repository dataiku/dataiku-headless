---
name: webapp-settings-structure-reference
description: "Settings and state structure reference for WebApp objects, for conservative round-trip editing guidance."
---

# WebApp Settings Structure Reference

Use this reference when editing WebApp settings through `get_webapp_settings` and `set_webapp_settings`.

## Settings Shape

In WebApp objects inspected on DSS:

- common top-level metadata fields are shared across WebApp types
- the main type-specific block lives in `params`
- `params` shape varies materially by WebApp type
- runtime state returned by `get_webapp_state` is minimal for stopped apps and richer for running apps
- some `STANDARD` WebApps include a top-level `apiKey` field

## Top-Level Fields

Common top-level fields:

- `type`
- `hasLegacyBackendURL`
- `projectKey`
- `id`
- `storageFile`
- `params`
- `config`
- `name`
- `versionTag`
- `creationTag`
- `tags`
- `checklists`
- `customFields`
- `isVirtual`
- conditional `apiKey`

Top-level field matrix:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `enum/string` | Common values include `STANDARD`, `DASH`, `BOKEH`, `SHINY`, `STREAMLIT`. |
| `hasLegacyBackendURL` | yes | `boolean` | Preserve as-is unless DSS changes it. |
| `projectKey` | yes | `string<project_key>` | Project context field returned by DSS. Preserve as-is. |
| `id` | yes | `string<webapp_id>` | WebApp id. Preserve as-is. |
| `storageFile` | yes | `string<path>` | DSS storage path. Preserve as-is. |
| `params` | yes | `object` | Main type-specific configuration block. See below. |
| `config` | yes | `object` | Often `{}` in inspected apps. Preserve when present. |
| `name` | yes | `string<any>` | Display name. Safe to edit intentionally. |
| `versionTag` | yes | `object` | DSS version metadata. Preserve. |
| `creationTag` | yes | `object` | DSS creation metadata. Preserve. |
| `tags` | yes | `list<string>` or `list<object>` | Metadata container. Preserve when present. |
| `checklists` | yes | `object` | Metadata container. Preserve when present. |
| `customFields` | yes | `object` | Metadata container. Preserve when present. |
| `isVirtual` | yes | `boolean` | Preserve as-is. |
| `apiKey` | conditional | `string<secret>` | Present on some `STANDARD` WebApps. Treat as sensitive and preserve. |

## `params` Model

`params` is the main type-specific block. Do not reconstruct it from scratch.

### Common cross-type `params` fields

Common cross-type fields:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `autoStartBackend` | common | `boolean` | Observed across all inspected types. |
| `envSelection` | common | `object` | Runtime environment selector. Preserve unless intentionally changing environment. |
| `infra` | common | `object` | Runtime/container/exposition block. Preserve unless intentionally changing deployment behavior. |
| `forceAuthentication` | common | `boolean` | Authentication toggle. Preserve unless intentionally changing access behavior. |

### `STANDARD` `params` fields

Common fields:

- `autoStartBackend`
- `backendAPIAccessEnabled`
- `backendEnabled`
- `backendFramework`
- `css`
- `enableJavascriptModules`
- `envSelection`
- `forceAuthentication`
- `hideJSSecurityPanel`
- `hideWebAppConfig`
- `html`
- `infra`
- `js`
- `libraries`
- `nbProcesses`
- `python`

`STANDARD` field notes:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `backendAPIAccessEnabled` | common | `boolean` | Seen with both `true` and `false`. |
| `backendEnabled` | common | `boolean` | Seen with both `true` and `false`. |
| `backendFramework` | common | `enum/string` | `FLASK` is a common value. |
| `html` | common | `string<any>` | Main HTML source for `STANDARD` apps. |
| `css` | common | `string<any>` | Main CSS source for `STANDARD` apps. |
| `js` | common | `string<any>` | Main JS source for `STANDARD` apps. |
| `python` | common | `string<any>` | Backend/server-side Python for `STANDARD` apps. |
| `libraries` | common | `list<object>` or `list<string>` | Preserve when present. |
| `enableJavascriptModules` | common | `boolean` | Preserve unless intentionally changing frontend behavior. |
| `hideJSSecurityPanel` | common | `boolean` | Preserve unless intentionally changing UI config behavior. |
| `hideWebAppConfig` | common | `boolean` | Preserve unless intentionally changing UI config behavior. |
| `nbProcesses` | common | `integer` | Preserve unless intentionally changing runtime concurrency. |

### `DASH` `params` fields

Common fields:

- `autoStartBackend`
- `backendAPIAccessEnabled`
- `envSelection`
- `forceAuthentication`
- `infra`
- `nbProcesses`
- `python`
- `serveLocally`

### `BOKEH` `params` fields

Common fields:

- `autoStartBackend`
- `envSelection`
- `forceAuthentication`
- `infra`
- `nbProcesses`
- `python`

### `SHINY` `params` fields

Common fields:

- `autoStartBackend`
- `envSelection`
- `forceAuthentication`
- `infra`
- `server`
- `ui`

### `STREAMLIT` `params` fields

Common fields:

- `autoStartBackend`
- `config`
- `envSelection`
- `forceAuthentication`
- `infra`
- `python`

## Nested Block Notes

### `envSelection`

Common shapes:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `envMode` | yes | `enum/string` | Common values: `INHERIT`, `EXPLICIT_ENV`. |
| `envName` | conditional | `string<code_env_name>` | Present when `envMode="EXPLICIT_ENV"`. |

### `infra.containerSelection`

Common shapes:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `containerMode` | yes | `enum/string` | Common values: `INHERIT`, `EXPLICIT_CONTAINER`. |
| `containerConf` | conditional | `string<container_conf_name>` | Present when `containerMode="EXPLICIT_CONTAINER"`. |

### `infra.exposition`

Common settings shape:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `enum/string` | `local_process` is a common value in settings. |
| `params` | yes | `object` | Often `{}` in inspected settings payloads. |

Additional `infra` fields commonly present:

- `overrideGlobalK8sExposition`
- `scaling`
- `podDisruptionBudget`
- `deploymentModifier`

Preserve all of these even when they appear inactive or defaulted.

## State Shape

### Minimal state

Common fields for stopped apps:

- `projectKey`
- `webAppId`
- `hasExposedEndpoint`

Minimal state matrix:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `projectKey` | yes | `string<project_key>` | Project context field. |
| `webAppId` | yes | `string<webapp_id>` | WebApp id in runtime state. |
| `hasExposedEndpoint` | yes | `boolean` | Indicates whether DSS currently reports an exposed endpoint. |

### Rich running state

Additional fields commonly present for running apps:

- `futureId`
- `futureInfo`
- `currentLogTail`
- `exposed`

Log-tail behavior:

- `currentLogTail` is a recent tail, not the full backend log
- `totalLines` indicates the total number of log lines available server-side
- `lines` contains only the recent returned slice
- `lastCrashLogTail` may appear after a failed startup and follows the same tail pattern

Common `exposed` fields:

| Field | Required | Domain | Notes |
| --- | --- | --- | --- |
| `expositionType` | yes | `enum/string` | Common values: `local_process`, `port_forward`. |
| `id` | yes | `string<any>` | Runtime exposure id; may be empty for local-process mode. |
| `scheme` | yes | `enum/string` | Observed: `http`. |
| `host` | yes | `string<host>` | Observed: `127.0.0.1`. |
| `port` | yes | `integer` | Runtime-local port. |
| `availability` | yes | `enum/string` | Observed: `LOCAL`. |
| `shouldAddPublicApiPath` | yes | `boolean` | Preserve interpretation from DSS state. |

## Sensitive Field Handling

Some `STANDARD` WebApps include top-level `apiKey`.

Rules:

- do not expose the actual value in user-facing output
- preserve it during round-trip edits
- if a tool redacts it, send the redacted field back unchanged or omit it so the current value can be preserved automatically

## Future Id Notes

Restart behavior:

- the `future_id` returned immediately by `restart_webapp_backend` tracks the restart action future
- `get_webapp_state.state.futureId` tracks the backend state/future reported by DSS after the restart
- these ids may differ and should not be assumed to match

## Recommended Update Pattern

- Always start from live `get_webapp_settings` output.
- Prefer narrow edits inside already-present fields rather than reconstructing the full object.
- Preserve top-level metadata containers such as `tags`, `customFields`, and `checklists`.
- Preserve runtime/configuration blocks such as `envSelection` and `infra` unless the user explicitly wants them changed.
- Preserve secrets such as `apiKey`.
- Do not remove nested blocks just because they appear inactive or defaulted.
- Do not guess absent nested keys; some settings vary by WebApp type and runtime mode.
- When changing one field, keep adjacent feature blocks unchanged unless the live settings show DSS changed them too.
